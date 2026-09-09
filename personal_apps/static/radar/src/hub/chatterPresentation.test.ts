import { describe, expect, it } from 'vitest'

import { feedLabel, sourcePresentation, tonePresentation } from './chatterPresentation'
import type { Tone } from '../types'

const tone = (bullish: number, bearish: number, neutral: number): Tone =>
  ({ bullish, bearish, neutral })

describe('tone, as a share of the directional sample', () => {
  it('reads the contract’s worked example', () => {
    // B=10, S=16, U=45 -> 38.5% bullish, bar 10:16, 26 directional / 71 total.
    // The nearby bucket mentions count is 68 in that example, which is why
    // `mentions` is never the denominator.
    const t = tonePresentation(tone(10, 16, 45))
    expect(t.kind).toBe('directional')
    expect(t.label).toBe('38.5% bullish')
    expect(t.sample).toBe('26 directional / 71 total')
    expect(t.bull).toBeCloseTo(10 / 26, 12)
    expect(t.bear).toBeCloseTo(16 / 26, 12)
  })

  it('draws the bar over the same denominator as the percentage', () => {
    const t = tonePresentation(tone(3, 1, 96))
    expect(t.label).toBe('75% bullish')
    expect(t.bull).toBe(0.75)
    expect(t.bear).toBe(0.25)
    // Not over the total: 3/100 would draw a sliver under a 75% label.
    expect(t.bull).not.toBeCloseTo(3 / 100, 3)
  })

  it('trims a trailing .0 rather than printing 50.0%', () => {
    expect(tonePresentation(tone(1, 1, 0)).label).toBe('50% bullish')
    expect(tonePresentation(tone(1, 3, 0)).label).toBe('25% bullish')
  })

  it('refuses to round a rare share away to zero', () => {
    // The specific objection to the old percentage: one bullish post in two
    // hundred must not read 0%.
    const t = tonePresentation(tone(1, 199, 0))
    expect(t.label).toBe('0.5% bullish')
    const rarer = tonePresentation(tone(1, 9999, 0))
    expect(rarer.label).toBe('<0.1% bullish')
    expect(rarer.bull).toBeGreaterThan(0)
  })

  it('refuses to round a near-total share up to a hundred', () => {
    expect(tonePresentation(tone(9999, 1, 0)).label).toBe('>99.9% bullish')
  })

  it('prints a true zero and a true hundred plainly', () => {
    expect(tonePresentation(tone(0, 4, 0)).label).toBe('0% bullish')
    expect(tonePresentation(tone(4, 0, 0)).label).toBe('100% bullish')
    // Zero contributes no segment rather than a hairline.
    expect(tonePresentation(tone(0, 4, 0)).bull).toBe(0)
    expect(tonePresentation(tone(4, 0, 0)).bear).toBe(0)
  })

  it('keeps the sample size visible on a sample of one', () => {
    const t = tonePresentation(tone(1, 0, 0))
    expect(t.label).toBe('100% bullish')
    expect(t.sample).toBe('1 directional / 1 total')
    // No invented confidence threshold, and no claim it is reliable.
    expect(t.detail).not.toMatch(/reliable|confident|significant/i)
  })

  it('says there is no direction rather than printing 0% or 50%', () => {
    const t = tonePresentation(tone(0, 0, 45))
    expect(t.kind).toBe('undirected')
    expect(t.label).toBe('No directional signal')
    expect(t.label).not.toMatch(/%/)
    expect(t.sample).toBe('45 unread or non-directional')
    expect(t.bull).toBeNull()
    expect(t.bear).toBeNull()
  })

  it('says there is no sample rather than inventing counts', () => {
    const t = tonePresentation(tone(0, 0, 0))
    expect(t.kind).toBe('unsampled')
    expect(t.label).toBe('No tone sample')
    expect(t.sample).toBeNull()
  })

  it('never calls the residual known neutral sentiment', () => {
    const t = tonePresentation(tone(10, 16, 45))
    expect(t.detail).toMatch(/not known neutral sentiment/i)
    expect(t.detail).toMatch(/balanced, mixed or unclear/i)
    expect(t.detail).toMatch(/nothing has classified yet/i)
  })

  it('never describes the percentage as a price or a recommendation', () => {
    for (const t of [tonePresentation(tone(10, 16, 45)),
                     tonePresentation(tone(0, 0, 3))]) {
      for (const text of [t.label, t.sample ?? '', t.detail]) {
        expect(text).not.toMatch(/chance|probab|rise|buy|invest|confidence/i)
      }
    }
  })

  it('reports malformed counts as unavailable rather than zero', () => {
    const bad: unknown[] = [
      { bullish: 1, bearish: 1, neutral: -1 },
      { bullish: NaN, bearish: 0, neutral: 0 },
      { bullish: Infinity, bearish: 0, neutral: 0 },
      { bullish: 1.5, bearish: 0, neutral: 0 },
      { bullish: '3', bearish: 0, neutral: 0 },
      { bullish: 1, bearish: 1 },
      null,
      undefined,
    ]
    for (const value of bad) {
      const t = tonePresentation(value as Tone)
      expect(t.kind).toBe('unavailable')
      expect(t.label).toBe('Tone unavailable')
      expect(t.sample).toBeNull()
      // Not coerced: an unavailable reading draws no bar at all.
      expect(t.bull).toBeNull()
    }
  })
})

describe('sources, as platforms rather than a wall of labels', () => {
  it('counts platforms and names them', () => {
    const s = sourcePresentation(['bluesky', 'fourchan', 'reddit:options'])
    expect(s.kind).toBe('platforms')
    expect(s.label).toBe('3 platforms')
    expect(s.summary).toContain('Reddit')
    expect(s.summary).toContain('Bluesky')
    expect(s.summary).toContain('4chan /biz/')
    expect(s.feedCount).toBe(3)
  })

  it('says one platform in the singular', () => {
    const s = sourcePresentation(['reddit:options'])
    expect(s.label).toBe('1 platform')
    expect(s.summary).toBe('Reddit')
  })

  it('folds many subreddits into one platform and keeps every identifier', () => {
    // The rejected board rendered thirty of these as `Reddit, Reddit, ...`.
    const subs = ['options', 'wallstreetbets', 'pennystocks', 'stocks']
      .map((sub) => `reddit:${sub}`)
    const s = sourcePresentation(subs)
    expect(s.label).toBe('1 platform')
    expect(s.summary).toBe('Reddit')
    expect(s.feedCount).toBe(4)
    expect(s.platforms).toHaveLength(1)
    expect(s.platforms[0].feeds).toEqual(
      ['r/options', 'r/pennystocks', 'r/stocks', 'r/wallstreetbets'])
  })

  it('caps the summary at two names plus a count when there are many', () => {
    const s = sourcePresentation(
      ['reddit:a', 'reddit:b', 'bluesky', 'fourchan', 'mastodon:eu'])
    expect(s.label).toBe('4 platforms')
    // Two named, and `+2` counts exactly the two it did not name.
    expect(s.summary).toBe('Reddit · 4chan /biz/ +2')
    expect(s.platforms.map((p) => p.label))
      .toEqual(['Reddit', '4chan /biz/', 'Bluesky', 'Mastodon'])
  })

  it('names all three when three is the whole list', () => {
    const s = sourcePresentation(['reddit:a', 'bluesky', 'fourchan'])
    expect(s.summary).toBe('4chan /biz/ · Bluesky · Reddit')
    expect(s.summary).not.toMatch(/\+/)
  })

  it('gives an unknown platform its own readable name', () => {
    // Never silently rooted into Reddit, and never left as a storage key.
    const s = sourcePresentation(['mastodon:social', 'telegram'])
    expect(s.platforms.map((p) => p.label)).toEqual(['Mastodon', 'Telegram'])
    expect(s.platforms[0].feeds).toEqual(['Mastodon · social'])
    expect(s.platforms[1].feeds).toEqual(['Telegram'])
  })

  it('distinguishes a measured empty list from a missing field', () => {
    const measured = sourcePresentation([])
    expect(measured.kind).toBe('none')
    expect(measured.label).toBe('No active feeds')
    expect(measured.feedCount).toBe(0)

    const missing = sourcePresentation(undefined)
    expect(missing.kind).toBe('unavailable')
    expect(missing.label).toBe('Source activity unavailable')
    expect(missing.summary).toBeNull()
    // Emphatically not a count. An older cached board measured nothing.
    expect(missing.label).not.toMatch(/^0\b/)
  })

  it('ignores junk entries instead of rendering them', () => {
    const s = sourcePresentation(['bluesky', '', null as unknown as string])
    expect(s.label).toBe('1 platform')
    expect(s.feedCount).toBe(1)
  })

  it('orders platforms by how many feeds each contributed', () => {
    const s = sourcePresentation(['bluesky', 'reddit:a', 'reddit:b'])
    expect(s.platforms.map((p) => p.label)).toEqual(['Reddit', 'Bluesky'])
  })
})

describe('feed labels', () => {
  it('names a subreddit the way its readers do', () => {
    expect(feedLabel('reddit:wallstreetbets')).toBe('r/wallstreetbets')
  })

  it('leaves a rootless feed as its platform', () => {
    expect(feedLabel('bluesky')).toBe('Bluesky')
    expect(feedLabel('fourchan')).toBe('4chan /biz/')
  })

  it('keeps a trailing colon from producing an empty name', () => {
    expect(feedLabel('reddit:')).toBe('Reddit')
  })
})
