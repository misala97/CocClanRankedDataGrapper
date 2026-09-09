// Find a company, anywhere in the universe.
//
// The universe and not the current board: a reader looking for a company
// nobody is discussing today still expects to find it, and a search that
// silently only covered the ranked rows would answer "nothing matches" about a
// company that plainly exists.
//
// The list is keyed by the query string in the shared cache, so a slow answer
// to a query the reader has moved on from cannot replace the list in front of
// them -- the race is closed by the key rather than by a sequence number the
// component has to remember to check.
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { exchangeLabel, segmentLabel } from '../format'
import type { SearchMatch } from '../types'
import { useSearch } from './queries'

/** How long typing has to go quiet before a request goes out. */
const SETTLE_MS = 250

export function Search({ onOpen }: { onOpen: (ticker: string) => void }) {
  const [typed, setTyped] = useState('')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const input = useRef<HTMLInputElement>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => setQuery(typed.trim()), SETTLE_MS)
    return () => clearTimeout(timer)
  }, [typed])

  const { data, isFetching } = useSearch(query)
  const matches: SearchMatch[] = data ?? []

  useEffect(() => {
    setActive(matches.length ? 0 : -1)
  }, [data])

  const pick = (ticker: string) => {
    onOpen(ticker)
    setOpen(false)
    setTyped('')
    setQuery('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' && open) {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp' && open) {
      event.preventDefault()
      setActive((index) => (matches.length ? Math.max(index - 1, 0) : -1))
    } else if (event.key === 'Enter' && open && active >= 0 && matches[active]) {
      event.preventDefault()
      pick(matches[active]!.ticker)
    } else if (event.key === 'Escape') {
      // In stages: the list, then the words, then the box. One Escape that
      // did all three would take the reader further back than they asked.
      event.preventDefault()
      if (open) setOpen(false)
      else if (typed) { setTyped(''); setQuery('') }
      else input.current?.blur()
    }
  }

  const listId = 'rh-search-list'
  const optionId = (ticker: string) => `rh-search-${ticker}`
  const showList = open && query.length > 0

  return (
    <div
      className="rh-search"
      ref={root}
      onBlur={(event) => {
        if (!root.current?.contains(event.relatedTarget as Node | null)) {
          setOpen(false)
        }
      }}
    >
      <label className="rh-visually-hidden" htmlFor="rh-search-input">
        Find a company
      </label>
      <input
        id="rh-search-input"
        ref={input}
        type="search"
        role="combobox"
        aria-label="Find a company"
        aria-expanded={showList}
        aria-controls={showList ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 && matches[active]
          ? optionId(matches[active]!.ticker) : undefined}
        placeholder="Find a company"
        value={typed}
        spellCheck={false}
        onChange={(event) => { setTyped(event.target.value); setOpen(true) }}
        onKeyDown={onKeyDown}
        onFocus={() => { if (typed.trim()) setOpen(true) }}
      />
      {showList && (
        <ul id={listId} role="listbox" className="rh-matches">
          {matches.map((match, index) => (
            <li
              key={match.ticker}
              id={optionId(match.ticker)}
              role="option"
              aria-selected={index === active}
              className={index === active ? 'active' : undefined}
              onMouseEnter={() => setActive(index)}
            >
              {/* mousedown is prevented so the input keeps focus and the list
                  does not close before the click lands. */}
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(match.ticker)}
              >
                <b>{match.ticker}</b>
                <span className="rh-name">{match.name ?? 'Name unknown'}</span>
                <span className="rh-sub">
                  {[exchangeLabel(match.exchange), segmentLabel(match.segment)]
                    .filter(Boolean).join(' · ')}
                </span>
              </button>
            </li>
          ))}
          {matches.length === 0 && (
            <li className="rh-nomatch" role="option" aria-selected="false">
              {isFetching ? 'Searching…' : 'Nothing matches that.'}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
