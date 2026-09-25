import { Fragment, useMemo } from 'react'
import type { HistoryEntry, HistoryPayload } from './types'
import { useHistoryUi } from './store'
import { Icon } from '../components/Icon'
import { instant, localParts, volume as de } from '../format'
import { apart, find, fold, isQuery, mentions } from '../search'
import { NearMisses } from '../components/NearMisses'
import { morphFrom } from '../vt'

/** An exercise's search text: the add sheet's, from the payload -- or its
 *  folded name, for one the payload has none for. */
const exerciseText = (payload: HistoryPayload, name: string) =>
  payload.exercise_search[name] ?? fold(name)


function Row({ entry, weekdayShort, hit }: {
  entry: HistoryEntry
  weekdayShort: string[]
  /** Whether an exercise of the row is what the search found it by; null
   *  while nothing is searched. */
  hit: ((exerciseName: string) => boolean) | null
}) {
  const exporting = useHistoryUi((s) => s.exporting)
  const selected = useHistoryUi((s) => s.selected.includes(entry.session_id))
  const toggle = useHistoryUi((s) => s.toggle)

  const started = localParts(entry.started_at)
  const pad = (n: number) => String(n).padStart(2, '0')
  const weekday = weekdayShort[started.weekday]
  const minutes = entry.finished_at === null
    ? 0
    : Math.floor(
      (instant(entry.finished_at).getTime() - instant(entry.started_at).getTime()) / 60000)
  const name = entry.name ?? 'Workout'

  return (
    <div className="row row--top verlauf__row">
      {exporting && (
        <label className="pick" aria-label={`${name} für Export auswählen`}>
          <input type="checkbox" className="export-row-check"
            value={entry.session_id} checked={selected}
            onChange={() => toggle(entry.session_id)} />
          <span className="pick__box" aria-hidden="true"><Icon name="check" /></span>
        </label>
      )}
      <a href={`/gym/session/${entry.session_id}`} className="row__main stack"
        onClick={morphFrom('session')}>
        <span className="row__name row__name--strong">{name}</span>
        {/* Weekday first: it is the one time dimension a training log is read
            for, and the band above already states the month. Sub-minute
            sessions printed "0 min" on 10 of 27 rows. A workout the app ended
            itself says so: its end is its last set, not a "Beenden" (D5). */}
        <span className="row__meta">
          {`${weekday} · ${pad(started.day)}.${pad(started.month)}. · ${pad(started.hour)}:${pad(started.minute)} · ${minutes < 1 ? '< 1' : minutes} min`
            + (entry.auto_finished ? ' · automatisch beendet' : '')}
        </span>
        {/* The roster is clipped on essentially every row. While a search
            runs, matching exercises float to the FRONT of the line (stable
            sort, so the rest keeps its order) and carry weight -- a hit that
            fell past the ellipsis looked like a false positive. */}
        <span className="row__sub">
          {(hit === null ? entry.exercises
            : [...entry.exercises].sort((a, b) => Number(hit(b)) - Number(hit(a)))
          ).map((exerciseName, i) => (
            <Fragment key={`${exerciseName}-${i}`}>
              {i > 0 && ' · '}
              {hit !== null && hit(exerciseName)
                ? <mark className="row__hit">{exerciseName}</mark>
                : exerciseName}
            </Fragment>
          ))}
        </span>
      </a>
      <span className="row__trail row__trail--stack">
        {/* .vol--none existed for this and was never applied: a session with
            no completed sets headlined a bold zero in the display face. */}
        {entry.volume
          ? <span className="vol">{de(entry.volume)}<small>kg</small></span>
          : <span className="vol vol--none">keine Sätze</span>}
        {entry.record_count > 0 && (
          <span className="vtag vtag--record">
            {`${entry.record_count} ${entry.record_count === 1 ? 'Rekord' : 'Rekorde'}`}
          </span>
        )}
        {/* Its own class: it borrowed vtag--neu, so restyling "Neu" would
            have silently recoloured Deload -- which must never carry a hue. */}
        {entry.is_deload && <span className="vtag vtag--deload">Deload</span>}
      </span>
    </div>
  )
}

export function HistoryPage({ payload }: { payload: HistoryPayload }) {
  const query = useHistoryUi((s) => s.query)
  const setQuery = useHistoryUi((s) => s.setQuery)
  const exporting = useHistoryUi((s) => s.exporting)
  const startExport = useHistoryUi((s) => s.startExport)
  const cancelExport = useHistoryUi((s) => s.cancelExport)
  const selected = useHistoryUi((s) => s.selected)
  const replaceSelection = useHistoryUi((s) => s.replaceSelection)

  // What each row is searched by: its name and date words, and each of its
  // exercises' texts -- the add sheet's, so a word that finds an exercise
  // in a workout finds the workouts that had it (G-145). This page matched
  // the bare names, lower-cased, and "bench" or "Bankdrucken" found nothing.
  const texts = useMemo(() => {
    const map = new Map<number, string>()
    for (const month of payload.months) {
      for (const entry of month.entries) {
        map.set(entry.session_id, apart([
          entry.search, ...entry.exercises.map((name) => exerciseText(payload, name)),
        ]))
      }
    }
    return map
  }, [payload])

  const found = useMemo(() => {
    if (!isQuery(query)) return null
    const entries = payload.months.flatMap((month) => month.entries)
    const { hits, tier } = find(entries, query, (e) => texts.get(e.session_id) ?? '')
    return { ids: new Set(hits.map((e) => e.session_id)), tier }
  }, [payload.months, texts, query])

  const shows = (entry: HistoryEntry) => found === null || found.ids.has(entry.session_id)
  // The exercises a row was found by float to the front of its line, marked.
  const hit = found === null ? null
    : (name: string) => mentions(exerciseText(payload, name), query, found.tier)

  const visible = payload.months
    .map((month) => ({ month, entries: month.entries.filter(shows) }))
    .filter(({ entries }) => entries.length > 0)
  const hitCount = visible.reduce((n, m) => n + m.entries.length, 0)

  /** Presets pick from what the search is showing, never from the whole list. */
  const pickWithin = (days: number | null) => {
    const cutoff = days === null ? null : Date.now() - days * 86_400_000
    replaceSelection(visible.flatMap(({ entries }) => entries
      .filter((e) => cutoff === null || instant(e.started_at).getTime() >= cutoff)
      .map((e) => e.session_id)))
  }

  return (
    <>
      <header className="verlauf__head">
        <h1 className="verlauf__h">Verlauf</h1>
        {/* aria-live, because search rewrites this and nothing else says how
            many results a query produced. */}
        <span className="verlauf__count" aria-live="polite">{hitCount}</span>
        <span className="start__sp" />
        {payload.total > 0 && (
          <button type="button" className="verlauf__act" aria-expanded={exporting}
            aria-controls="export-panel"
            onClick={() => (exporting ? cancelExport() : startExport())}>
            Exportieren
          </button>
        )}
      </header>

      {payload.total > 0 ? (
        <>
          <div className="searchbar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
            </svg>
            <input type="search" id="verlauf-search" className="searchbar__input"
              placeholder="Workout oder Übung…" autoComplete="off"
              aria-label="Verlauf durchsuchen"
              value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>

          {exporting && (
            <div className="export" id="export-panel">
              <div className="export__row">
                <span className="label">{`${selected.length} ausgewählt`}</span>
                <span className="start__sp" />
                <button type="button" className="export__cancel"
                  onClick={cancelExport}>Abbrechen</button>
              </div>
              {/* Every preset selects only rows the search is currently
                  showing, and says so. */}
              <div className="export__presets">
                <button type="button" className="preset export-preset"
                  onClick={() => pickWithin(30)}>30 Tage</button>
                <button type="button" className="preset export-preset"
                  onClick={() => pickWithin(90)}>90 Tage</button>
                <button type="button" className="preset export-preset"
                  onClick={() => pickWithin(null)}>Alle sichtbaren</button>
              </div>
              {/* A real <button>, not an <a> whose href gets removed: without
                  an href an anchor has no link role, drops out of the tab
                  order and announces nothing, so the disabled state of the
                  mode's only action was invisible to assistive tech. */}
              <button type="button"
                className={selected.length === 0 ? 'export__go is-disabled' : 'export__go'}
                disabled={selected.length === 0}
                onClick={() => {
                  window.location.href = `/gym/export?ids=${selected.join(',')}`
                }}>Als JSON exportieren</button>
            </div>
          )}

          {hitCount === 0 && (
            <p className="empty" role="status">
              Kein Workout gefunden für <b>{query.trim()}</b>.{' '}
              <button type="button" className="linklike"
                onClick={() => setQuery('')}>Suche zurücksetzen</button>
            </p>
          )}
          {hitCount > 0 && found?.tier === 'typos' && <NearMisses query={query} />}

          <div id="verlauf-list">
            {visible.map(({ month, entries }) => (
              <section className="month-group" key={month.slug}
                aria-labelledby={`m-${month.slug}`}>
                <div className="month">
                  <h2 className="label" id={`m-${month.slug}`}>{month.label}</h2>
                  <span className="start__sp" />
                  <span className="label">
                    {`${entries.length} ${entries.length === 1 ? 'Workout' : 'Workouts'}`}
                  </span>
                  {/* A month whose only sessions logged nothing has no total to
                      state, and "0 kg" under a heading reads as a bad month
                      rather than an empty one. */}
                  {month.volume > 0 && (
                    <span className="month__sum">
                      {`${de(month.volume)} kg${month.records ? ` · ${month.records} ${month.records === 1 ? 'Rekord' : 'Rekorde'}` : ''}`}
                    </span>
                  )}
                </div>

                {entries.map((entry) => (
                  <div key={entry.session_id}>
                    {/* A break in training is the most important thing a
                        history can show and it was shown by nothing: rows sit
                        at equal spacing whether they are one day or six weeks
                        apart. */}
                    {entry.gap_days !== null && entry.gap_days >= payload.gap_threshold && (
                      <p className="gap">{`${entry.gap_days} Tage Pause`}</p>
                    )}
                    <Row entry={entry} weekdayShort={payload.weekday_short} hit={hit} />
                  </div>
                ))}
              </section>
            ))}
          </div>
        </>
      ) : (
        <p className="empty">
          Noch keine abgeschlossenen Workouts.<br />
          <a href="/gym">Auf Start ein Workout beginnen</a>
        </p>
      )}
    </>
  )
}
