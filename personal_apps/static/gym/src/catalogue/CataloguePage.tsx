import { Fragment, useEffect, useMemo, useState } from 'react'
import type { CatalogueEntry, CataloguePayload, LibraryEntry, RestOverview, SortMode } from './types'
import { recency, sincePr } from './format'
import { kg } from '../format'
import { apart, find, fold, isQuery } from '../search'
import { sections } from '../session/picker'
import { bandOpen, useCatalogueUi } from './store'
import { morphFrom } from '../vt'
import { Icon } from '../components/Icon'
import { NearMisses } from '../components/NearMisses'
import { PictureTile } from '../session/components/Picture'
import { RestSheet, exceptionCount, listRange } from '../settings/RestSheet'
import { clock } from '../settings/values'
import { Band, bandCount, slug } from './Band'
import { NeverDone } from './NeverDone'

const SORTS: { mode: SortMode; label: string }[] = [
  { mode: 'muscle', label: 'Nach Muskelgruppe' },
  { mode: 'stall', label: 'Stagniert zuerst' },
  { mode: 'recent', label: 'Zuletzt trainiert' },
]

function ExerciseRow({ entry, group }: {
  entry: CatalogueEntry
  group: string
}) {
  const stall = sincePr(entry.sessions_since_pr)
  // Yours with no set yet -- kept in a routine, set up, added and not done:
  // "Noch nie gemacht" is the part below now, the list's rest. Lifted in the
  // running workout, it has sets, just none finished (its page says so too).
  const when = entry.days_ago !== null ? recency(entry.days_ago)
    : entry.in_running ? 'Heute im Workout' : 'Noch kein Satz'
  const meta = when + (stall ? ` · ${stall}` : '')

  return (
    // The whole row is the link. The two figures used to sit outside it, so
    // link-list navigation announced the name and never the weight.
    <a className="row row--top uebungen-row has-pic"
      href={`/gym/exercises/${entry.exercise.id}`}
      onClick={morphFrom('ex', '.nameline__n')}
      data-group={group}>
      <PictureTile src={entry.picture} size="list" />
      <span className="row__main stack">
        <span className="nameline">
          <span className="nameline__n">{entry.exercise.name}</span>
          {entry.chip_label !== null && (
            <span className={`vtag vtag--${entry.chip_class}`}>{entry.chip_label}</span>
          )}
        </span>
        <span className="row__meta">{meta}</span>
      </span>
      {/* Leads with the weight you would put on the bar today. It led with the
          all-time best, unlabelled -- so a row reading "15,0 kg" could not be
          told apart from a working weight. */}
      <span className="row__trail row__trail--stack">
        {entry.last_weight !== null ? (
          <>
            {/* "je Seite" on unilateral lifts. Without it the catalogue -- the
                one surface whose job is comparing exercises -- showed a
                per-side load above a bilateral one, which is the same weight
                read as half. */}
            <span className="vol">
              {kg(entry.last_weight)}
              <small>{entry.exercise.is_unilateral ? 'kg/Seite' : 'kg'}</small>
            </span>
            <span className="lastline">
              {entry.best_weight !== null && entry.best_weight > entry.last_weight
                ? `zuletzt · best ${kg(entry.best_weight)}`
                : 'zuletzt'}
            </span>
          </>
        ) : (
          <span className="vol vol--none">—</span>
        )}
      </span>
    </a>
  )
}

/** "Deine Pause", above the exercises it applies to: what it is now, and the
 *  sheet that changes it. */
function RestRow({ rest, onOpen }: { rest: RestOverview; onOpen(): void }) {
  const forAll = rest.rest_for_all
  return (
    <div className="uebungen-rest">
      <button type="button" className="sheet-row" onClick={onOpen}>
        <span className="sheet-row__lead"><Icon name="timer" /></span>
        <span className="sheet-row__main">
          <span className="sheet-row__name">Deine Pause</span>
          {/* Two phrases that each stay whole: a narrow row breaks between
              them, never inside "12 eigene". */}
          <span className="sheet-row__meta">
            <span>{forAll !== null ? 'Für alle Übungen' : 'Je nach Übungsart'}</span>
            {rest.exceptions.length > 0 && <>{' · '}<span>{exceptionCount(rest)}</span></>}
          </span>
        </span>
        <span className="sheet-row__val">{forAll !== null ? clock(forAll) : listRange(rest)}</span>
        <span className="sheet-row__chev"><Icon name="forward" /></span>
      </button>
    </div>
  )
}

/** The groups of the list with nothing of yours, in one line under your
 *  bands (G-013) -- each a jump to its band of the rest, opened. A group the
 *  rest has no band for (all of it yours, under another muscle) is named
 *  and not linked. */
function NothingFor({ names, bands, onJump }: {
  names: string[]
  bands: Set<string>
  onJump(name: string): void
}) {
  return (
    <p className="ueb-none">
      {'Noch nichts für '}
      {names.map((name, i) => (
        <Fragment key={name}>
          {i === 0 ? '' : i === names.length - 1 ? ' und ' : ', '}
          {bands.has(name)
            ? <a href={`#nie-${slug(name)}`} onClick={() => onJump(name)}>{name}</a>
            : name}
        </Fragment>
      ))}
      .
    </p>
  )
}

/** A row of yours, with the band it is in and what the search looks in. */
interface OwnRow { own: true; entry: CatalogueEntry; group: string; search: string }
/** A row of the rest of the list. */
interface ListRow { own: false; entry: LibraryEntry; search: string }

/**
 * Übungen (M6, D13-A): the lifter's own exercises -- the ones they logged,
 * keep in a routine or set up -- and under them the rest of the one list,
 * "Noch nie gemacht". Nothing is created here: every exercise is the list's,
 * and a new one is begun from its page or added in a workout.
 */
export function CataloguePage({ payload }: { payload: CataloguePayload }) {
  // The sheet's answers, so the row says what was just set.
  const [rest, setRest] = useState(payload.rest)
  const [restOpen, setRestOpen] = useState(false)
  const query = useCatalogueUi((s) => s.query)
  const setQuery = useCatalogueUi((s) => s.setQuery)
  const sort = useCatalogueUi((s) => s.sort)
  const setSort = useCatalogueUi((s) => s.setSort)
  const open = useCatalogueUi((s) => s.open)
  const toggleGroup = useCatalogueUi((s) => s.toggleGroup)
  const openNie = useCatalogueUi((s) => s.openNie)

  // `/` focuses the search from anywhere on the page -- the desktop dividend
  // on the one page that is mostly a search box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
        || target.tagName === 'SELECT' || target.isContentEditable) return
      e.preventDefault()
      document.getElementById('uebungen-search')?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const searching = isQuery(query)
  const groupNames = payload.groups.map((g) => g.name)

  // Every row with what the search looks in: the add sheet's text -- aliases,
  // English names -- and its band's name, so "Beine" finds them. One search
  // for both parts, so one tier: a typo's near misses are never shown beside
  // exact hits of the other part.
  const ownRows = useMemo(
    () => payload.groups.flatMap((g) => g.entries.map((entry): OwnRow => ({
      own: true, entry, group: g.name, search: apart([entry.search, fold(g.name)]),
    }))),
    [payload.groups])
  const listRows = useMemo(
    () => payload.library.map((entry): ListRow => ({
      own: false, entry, search: apart([entry.search, fold(entry.movement_group)]),
    })),
    [payload.library])

  const found = useMemo(
    () => (searching
      ? find<OwnRow | ListRow>([...ownRows, ...listRows], query, (r) => r.search)
      : null),
    [ownRows, listRows, query, searching])
  const hits = useMemo(
    () => (found === null ? ownRows : found.hits.filter((r): r is OwnRow => r.own)),
    [found, ownRows])
  const listHits = useMemo(
    () => (found === null
      ? payload.library
      : found.hits.flatMap((r) => (r.own ? [] : [r.entry]))),
    [found, payload.library])

  const flat = useMemo(() => {
    const compareStall = (a: OwnRow, b: OwnRow) =>
      (b.entry.sessions_since_pr ?? -1) - (a.entry.sessions_since_pr ?? -1)
    const compareRecent = (a: OwnRow, b: OwnRow) =>
      (b.entry.last_done ?? '').localeCompare(a.entry.last_done ?? '')
    return [...hits].sort(sort === 'recent' ? compareRecent : compareStall)
  }, [hits, sort])

  // The rest in its bands: all of it for each band's size and for the jumps
  // of "Noch nichts für", the hits for what shows.
  const listed = useMemo(
    () => sections(payload.library, payload.list_groups),
    [payload.library, payload.list_groups])
  const shownList = useMemo(
    () => (found === null ? listed : sections(listHits, payload.list_groups)),
    [found, listed, listHits, payload.list_groups])
  const sizes = useMemo(
    () => new Map(listed.map((s) => [s.group, s.movements.reduce((n, m) => n + m.rows.length, 0)])),
    [listed])

  const ownTotal = ownRows.length
  const hitCount = hits.length + listHits.length
  const banded = searching || sort === 'muscle'
  const empty = payload.groups.filter((g) => g.entries.length === 0).map((g) => g.name)

  return (
    // No wrapper: the mount node in uebungen.html already IS .uebungen.
    <>
      <header className="verlauf__head">
        <h1 className="verlauf__h">Übungen</h1>
      </header>

      {/* Before a first workout too: a new lifter sets their rest first. */}
      <RestRow rest={rest} onOpen={() => setRestOpen(true)} />
      <RestSheet overview={rest} open={restOpen} onClose={() => setRestOpen(false)}
        onSaved={setRest} />

      <div className="searchbar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
        </svg>
        <input type="search" id="uebungen-search" className="searchbar__input"
          placeholder="Übung suchen…" autoComplete="off"
          aria-label="Übungen durchsuchen"
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            // Enter opens the first hit: type three letters, Enter, done.
            // The first as shown: yours come first, in their bands (a
            // search bands them whatever the sort); none of yours, the
            // rest's first.
            if (e.key !== 'Enter' || !searching) return
            const own = hits[0]
            const id = own !== undefined
              ? own.entry.exercise.id
              : shownList[0]?.movements[0]?.rows[0]?.id
            if (id !== undefined) window.location.href = `/gym/exercises/${id}`
          }} />
      </div>

      {searching && hitCount === 0 && (
        <p className="empty" role="status">
          Keine Übung gefunden für <b>{query.trim()}</b>.{' '}
          <button type="button" className="linklike"
            onClick={() => setQuery('')}>Suche zurücksetzen</button>
        </p>
      )}
      {hitCount > 0 && found?.tier === 'typos' && <NearMisses query={query} />}
      {/* The part heads show the hits; this says them. */}
      <p className="sr-only" role="status">
        {searching && hitCount > 0 ? `${hits.length} eigene, ${listHits.length} aus der Liste` : ''}
      </p>

      {(!searching || hits.length > 0) && (
        <section className="ueb-part" aria-labelledby="deine-h">
          <h2 className="ueb-part__h" id="deine-h">
            Deine
            {ownTotal > 0 && <>{' '}<span className="ueb-part__n">{hits.length}</span></>}
          </h2>
          {ownTotal === 0 ? (
            <p className="ueb-part__lead">
              Noch keine. Was du im Workout loggst, steht danach hier, mit deinem
              Gewicht und deinen Einstellungen.
            </p>
          ) : (
            <>
              {/* The sorts order a list to browse. A search shows its hits
                  in their bands, like the rest's, each with "N von M". */}
              {!searching && (
                <div className="sorts" role="group" aria-label="Übungen ordnen">
                  {SORTS.map(({ mode, label }) => (
                    <button key={mode} type="button"
                      className={sort === mode ? 'sort is-on' : 'sort'}
                      aria-pressed={sort === mode}
                      onClick={() => setSort(mode)}>{label}</button>
                  ))}
                </div>
              )}

              <div id="uebungen-list" className={banded ? undefined : 'is-flat'}>
                {banded
                  ? payload.groups.map((group) => {
                    const groupHits = hits.filter((r) => r.group === group.name)
                    // Nothing of yours here: named once under the list.
                    if (groupHits.length === 0) return null
                    // A searching reader wants the matches, not their
                    // folders, so a query opens every band that has one.
                    const expanded = searching || bandOpen(open, group.name, payload.open_by_default)
                    return (
                      <section className="group-sec" key={group.name}
                        aria-labelledby={`g-${slug(group.name)}`}>
                        <Band id={`g-${slug(group.name)}`} name={group.name} expanded={expanded}
                          count={bandCount(groupHits.length, group.entries.length, searching)}
                          onToggle={() => toggleGroup(
                            group.name, payload.open_by_default, groupNames)} />
                        {expanded && groupHits.map(({ entry }) => (
                          <ExerciseRow key={entry.exercise.id} entry={entry}
                            group={group.name} />
                        ))}
                      </section>
                    )
                  })
                  : flat.map(({ entry, group }) => (
                    <ExerciseRow key={entry.exercise.id} entry={entry} group={group} />
                  ))}
              </div>
              {!searching && empty.length > 0 && (
                <NothingFor names={empty} bands={new Set(listed.map((s) => s.group))}
                  onJump={openNie} />
              )}
            </>
          )}
        </section>
      )}

      {payload.library.length > 0 && (!searching || listHits.length > 0) && (
        <NeverDone shown={shownList} sizes={sizes} searching={searching}
          count={listHits.length} hasOwn={ownTotal > 0} />
      )}
    </>
  )
}

