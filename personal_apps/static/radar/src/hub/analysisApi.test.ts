import { afterEach, describe, expect, it, vi } from 'vitest'

import { AnalysisUnavailable, TIMEOUT_MS, fetchAnalysis, fetchAnalysisResolve } from './analysisApi'
import { analysis, resolved } from './analysisFixtures'
import {
  defaultRange, priceRuns, rangeProblem, todayUtc, chatterLabel, priceStateLabel,
} from './analysisTypes'
import { chatterDay, priceDay } from './analysisFixtures'

function reply(body: unknown, init: { status?: number; type?: string; redirected?: boolean } = {}) {
  const status = init.status ?? 200
  const type = init.type ?? 'application/json'
  const response = new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status, headers: { 'content-type': type },
  })
  if (init.redirected) Object.defineProperty(response, 'redirected', { value: true })
  return response
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('the analysis requests (C11/C12)', () => {
  it('asks the exact resolve and company URLs with no board filters', async () => {
    const fetched = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(reply(resolved()))
      .mockResolvedValueOnce(reply(analysis()))
    await fetchAnalysisResolve('BRK.B')
    await fetchAnalysis(11, 7, { from: '2026-09-07', to: '2026-09-13' })
    const urls = fetched.mock.calls.map((call) => String(call[0]))
    expect(urls[0]).toBe('/radar/api/analysis/resolve?ticker=BRK.B')
    expect(urls[1]).toBe('/radar/api/analysis/company/11?instrument_id=7&from=2026-09-07&to=2026-09-13')
    for (const url of urls) {
      for (const key of ['market', 'sources', 'window', 'span', 'sort']) {
        expect(url).not.toContain(`${key}=`)
      }
    }
    const init = fetched.mock.calls[1]![1] as RequestInit
    expect((init.headers as Record<string, string>).Accept).toBe('application/json')
    expect(init.credentials).toBe('same-origin')
  })

  it('maps every refusal to its own reason and keeps the server code', async () => {
    const cases: [number, string, string][] = [
      [404, 'unknown_company', 'missing'], [409, 'identity_changed', 'conflict'],
      [422, 'ineligible_instrument', 'unsupported'], [400, 'reversed_range', 'invalid'],
      [503, 'analysis_limit', 'limit'], [503, 'analysis_unavailable', 'unavailable'],
      [403, 'x', 'forbidden'], [500, 'x', 'server'],
    ]
    for (const [status, code, reason] of cases) {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        reply({ error: 'said so', code }, { status }))
      const error = await fetchAnalysisResolve('AAA').catch((e: unknown) => e)
      expect(error).toBeInstanceOf(AnalysisUnavailable)
      expect((error as AnalysisUnavailable).reason).toBe(reason)
      expect((error as AnalysisUnavailable).code).toBe(code)
      vi.restoreAllMocks()
    }
  })

  it('reads a login page as an expired session, never as data', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      reply('<html>login</html>', { type: 'text/html', redirected: true }))
    const error = await fetchAnalysis(11, 7, { from: '2026-09-07', to: '2026-09-13' })
      .catch((e: unknown) => e)
    expect((error as AnalysisUnavailable).reason).toBe('session')
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      reply('<html>login</html>', { type: 'text/html' }))
    const html = await fetchAnalysisResolve('AAA').catch((e: unknown) => e)
    expect((html as AnalysisUnavailable).reason).toBe('session')
  })

  it('times out after eight seconds and does not retry by itself', async () => {
    vi.useFakeTimers()
    const fetched = vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_url, init) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const abort = new Error('aborted')
          abort.name = 'AbortError'
          reject(abort)
        })
      }))
    const pending = fetchAnalysisResolve('AAA').catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)
    const error = await pending
    expect((error as AnalysisUnavailable).reason).toBe('timeout')
    expect(fetched).toHaveBeenCalledTimes(1)
  })

  it('relays the caller’s abort', async () => {
    const controller = new AbortController()
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_url, init) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const abort = new Error('aborted')
          abort.name = 'AbortError'
          reject(abort)
        })
      }))
    const pending = fetchAnalysisResolve('AAA', controller.signal).catch((e: unknown) => e)
    controller.abort()
    expect(((await pending) as AnalysisUnavailable).reason).toBe('timeout')
  })

  it('treats an unreachable server as network', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('offline'))
    const error = await fetchAnalysisResolve('AAA').catch((e: unknown) => e)
    expect((error as AnalysisUnavailable).reason).toBe('network')
  })
})

describe('the window (C01 client side)', () => {
  const now = new Date('2026-09-14T12:30:00Z')

  it('defaults to the last seven completed UTC days', () => {
    expect(todayUtc(now)).toBe('2026-09-14')
    expect(defaultRange(now)).toEqual({ from: '2026-09-07', to: '2026-09-13' })
    expect(defaultRange(new Date('2026-09-14T23:59:00Z'))).toEqual({ from: '2026-09-07', to: '2026-09-13' })
    expect(defaultRange(new Date('2026-09-15T00:00:00Z'))).toEqual({ from: '2026-09-08', to: '2026-09-14' })
  })

  it('refuses what the server would refuse, without repairing it', () => {
    expect(rangeProblem({ from: '2026-09-07', to: '2026-09-13' }, now)).toBeNull()
    expect(rangeProblem({ from: '2026-09-13', to: '2026-09-13' }, now)).toBeNull()
    expect(rangeProblem({ from: '2026-03-02', to: '2026-03-04' }, now)).toBeNull()
    expect(rangeProblem({ from: '2026-09-13', to: '2026-09-07' }, now)).toBe('reversed_range')
    expect(rangeProblem({ from: '2026-09-06', to: '2026-09-13' }, now)).toBe('range_too_long')
    expect(rangeProblem({ from: '2026-09-08', to: '2026-09-14' }, now)).toBe('range_not_completed')
    expect(rangeProblem({ from: '2026-02-29', to: '2026-03-01' }, now)).toBe('invalid_date')
    expect(rangeProblem({ from: '2026-9-7', to: '2026-09-13' }, now)).toBe('invalid_date')
    expect(rangeProblem({ from: '', to: '2026-09-13' }, now)).toBe('invalid_date')
  })
})

describe('what the line may join (C03/C05, SPEC section 3, REVIEW-1 P2-1/R5)', () => {
  it('joins only adjacent observed dates in one regime; a modeled-closed weekend breaks the line', () => {
    const days = [
      priceDay('2026-09-10', { close: 1 }), priceDay('2026-09-11', { close: 2 }),
      priceDay('2026-09-12'), priceDay('2026-09-13'), priceDay('2026-09-14', { close: 3 }),
    ]
    days[4]!.calendar_hint = 'modeled_open'
    expect(days[2]!.calendar_hint).toBe('modeled_closed')
    // Thu-Fri joined; Monday stands alone across the weekend. Nothing bridged.
    expect(priceRuns(days)).toEqual([[0, 1], [4]])
  })

  it('breaks at a missing open day, an invalid row, an unverified date and a regime change', () => {
    const days = [
      priceDay('2026-09-08', { close: 1 }), priceDay('2026-09-09'),
      priceDay('2026-09-10', { close: 2 }), priceDay('2026-09-11', { close: 3, regime: 'us/XNYS/USD/finnhub/close/split' }),
      priceDay('2026-09-12'), priceDay('2026-09-13'),
      priceDay('2026-09-14', { close: 4, regime: 'us/XNYS/USD/finnhub/close/split' }),
    ]
    days[6]!.calendar_hint = 'modeled_open'
    // 8 alone (9 is missing); 10 alone (11 changed source); 11 alone and 14
    // alone, even in the same finnhub regime, because the weekend is between.
    expect(priceRuns(days)).toEqual([[0], [2], [3], [6]])
    const aba = [
      priceDay('2026-09-08', { close: 1 }),
      priceDay('2026-09-09', { close: 2, regime: 'us/XNYS/USD/finnhub/close/split' }),
      priceDay('2026-09-10', { close: 3 }), priceDay('2026-09-11', { close: 4 }),
    ]
    expect(priceRuns(aba)).toEqual([[0], [1], [2, 3]])
    const invalid = [
      priceDay('2026-09-08', { close: 1 }),
      priceDay('2026-09-09', { state: 'invalid', reason: 'currency is not USD', source: 'finnhub' }),
      priceDay('2026-09-10', { close: 2 }),
    ]
    expect(priceRuns(invalid)).toEqual([[0], [2]])
    const unverified = [
      priceDay('2026-09-08', { close: 1 }),
      priceDay('2026-09-09', { state: 'identity_unverified' }),
      priceDay('2026-09-10', { close: 2 }),
    ]
    expect(priceRuns(unverified)).toEqual([[0], [2]])
    const unknown = [priceDay('2026-09-11', { close: 1 }), priceDay('2026-09-12'), priceDay('2026-09-13', { close: 2 })]
    unknown[1]!.calendar_hint = 'unknown'
    expect(priceRuns(unknown)).toEqual([[0], [2]])
  })

  it('a sole close is a dot', () => {
    expect(priceRuns([priceDay('2026-09-09', { close: 1 })])).toEqual([[0]])
    expect(priceRuns([])).toEqual([])
  })
})

describe('the words for a day', () => {
  it('never calls a partial zero “no chatter”', () => {
    expect(chatterLabel(chatterDay('2026-09-09', { mentions: 0, coverage: 'partial' })))
      .toBe('0 in observed buckets — coverage incomplete')
    expect(chatterLabel(chatterDay('2026-09-09', { mentions: 0, coverage: 'observed' }))).toBe('0 observed')
    expect(chatterLabel(chatterDay('2026-09-09'))).toBe('no retained buckets')
    expect(chatterLabel(chatterDay('2026-09-09', { overlap_ambiguous: true, coverage: 'partial' })))
      .toContain('withheld')
  })

  it('distinguishes a closed day from a retained gap', () => {
    expect(priceStateLabel(priceDay('2026-09-12'))).toContain('modeled closed')
    expect(priceStateLabel(priceDay('2026-09-09'))).toContain('modeled open')
    expect(priceStateLabel(priceDay('2026-09-09', { state: 'invalid', reason: 'x' }))).toContain('unusable')
    expect(priceStateLabel(priceDay('2026-09-09', { state: 'identity_unverified' }))).toContain('company record')
  })
})
