import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { fetchSearch } from '../api'
import { exchangeLabel, segmentLabel } from '../format'
import { scoreText } from '../list/TickerRow'
import type { Row, SearchMatch } from '../types'

/** How long typing has to go quiet before a request goes out. */
const SETTLE_MS = 150

/** Find a stock by symbol or name, anywhere in the universe.
 *
 *  A combobox in the masthead: `/` reaches it from anywhere, the arrows walk
 *  the matches, Enter opens the panel -- for a stock on the board or not,
 *  through the same path a row click takes. Each match is annotated from
 *  what the page already holds (on the board with its score, watching,
 *  or quiet today); the endpoint returns identity only.
 */
export function Search({ rows, watching, onPick, onToggleWatch }: {
  rows: Row[]
  watching: string[]
  onPick: (ticker: string) => void
  onToggleWatch?: (ticker: string) => void
}) {
  const [q, setQ] = useState('')
  const [matches, setMatches] = useState<SearchMatch[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const input = useRef<HTMLInputElement>(null)
  const root = useRef<HTMLDivElement>(null)
  // The request that may still publish. A slow answer to an old query must
  // not replace the list the reader is looking at.
  const latest = useRef(0)

  // `/` focuses, as on GitHub -- unless the reader is already typing.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
                     || target.isContentEditable)) return
      event.preventDefault()
      input.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const here = () => Boolean(root.current?.contains(document.activeElement))

  useEffect(() => {
    const query = q.trim()
    const mine = ++latest.current
    if (!query) {
      setMatches([]); setOpen(false); setActive(-1)
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetchSearch(query, controller.signal).then((found) => {
        if (mine !== latest.current) return
        setMatches(found); setActive(found.length ? 0 : -1)
        // Open only while the reader is still here: a response landing
        // after focus left must not float the list over whatever they
        // moved to. The results are kept; coming back shows them.
        if (here()) setOpen(true)
      }).catch(() => {
        if (mine !== latest.current) return
        setMatches([]); setActive(-1)
        if (here()) setOpen(true)
      })
    }, SETTLE_MS)
    return () => { clearTimeout(timer); controller.abort() }
  }, [q])

  const status = (match: SearchMatch): string => {
    const onBoard = rows.find((r) => r.ticker === match.ticker)
    if (onBoard) return `on the board · ${scoreText(onBoard)}`
    if (watching.includes(match.ticker) || match.watching) return 'watching'
    return 'quiet today'
  }

  const pick = (ticker: string) => {
    onPick(ticker)
    setOpen(false)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' && open) {
      event.preventDefault(); setActive((i) => Math.min(i + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp' && open) {
      event.preventDefault(); setActive((i) => matches.length ? Math.max(i - 1, 0) : -1)
    } else if (event.key === 'Enter' && open && active >= 0 && matches[active]) {
      event.preventDefault(); pick(matches[active]!.ticker)
    } else if (event.key === 'Escape') {
      // In stages: the list, then the words, then the box.
      event.preventDefault()
      if (open) setOpen(false)
      else if (q) setQ('')
      else input.current?.blur()
    }
  }

  const listId = 'radar-search-list'
  const optionId = (ticker: string) => `radar-search-${ticker}`

  return (
    <div className="search" ref={root}
         onBlur={(event) => {
           // Focus moving within the search (input <-> a match's buttons) keeps
           // the list; focus leaving it -- a row, the market switch, Tab out --
           // closes it. The buttons' mousedown is prevented, so a click never
           // blurs the input in the first place.
           if (!root.current?.contains(event.relatedTarget as Node | null)) setOpen(false)
         }}>
      <input ref={input} type="search" role="combobox" aria-label="Find a stock"
             aria-expanded={open} aria-controls={open ? listId : undefined} aria-autocomplete="list"
             aria-activedescendant={open && active >= 0 && matches[active]
               ? optionId(matches[active]!.ticker) : undefined}
             placeholder="Find a stock" value={q} spellCheck={false}
             onChange={(event) => setQ(event.target.value)}
             onKeyDown={onKeyDown}
             onFocus={() => { if (matches.length || q.trim()) setOpen(Boolean(q.trim())) }} />
      {open && (
        <ul id={listId} role="listbox" className="matches">
          {matches.map((match, index) => {
            const isWatching = watching.includes(match.ticker)
            const label = [match.ticker, match.name,
              [exchangeLabel(match.exchange), segmentLabel(match.segment)].filter(Boolean).join(' · '),
              status(match)].filter(Boolean).join(', ')
            return (
            <li key={match.ticker} id={optionId(match.ticker)} role="option"
                aria-selected={index === active}
                aria-label={label}
                className={index === active ? 'active' : undefined}
                onMouseEnter={() => setActive(index)}>
              {/* mousedown is prevented so the input keeps focus and the
                  list does not close before the click lands. */}
              <button type="button" className="pick"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => pick(match.ticker)}>
                <b>{match.ticker}</b>
                <span className="nm">{match.name ?? '—'}</span>
                <span className="meta">
                  {[exchangeLabel(match.exchange), segmentLabel(match.segment)]
                    .filter(Boolean).join(' · ')}
                </span>
                <span className="st">{status(match)}</span>
              </button>
              {onToggleWatch && (
                <button type="button"
                        className={`star${isWatching ? ' on' : ''}`}
                        aria-pressed={isWatching}
                        aria-label={`${isWatching ? 'Stop watching' : 'Watch'} ${match.ticker}`}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => onToggleWatch(match.ticker)}>
                  {isWatching ? '★' : '☆'}
                </button>
              )}
            </li>
            )
          })}
          {matches.length === 0 && (
            <li className="none" role="option" aria-selected="false">Nothing matches</li>
          )}
        </ul>
      )}
    </div>
  )
}
