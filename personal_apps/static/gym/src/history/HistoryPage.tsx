import { Fragment, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type {
  HistoryEntry, HistoryIndexMonth, HistoryPayload, HistoryRecord, HistorySummary, HistoryWeeks,
} from './types'
import { useHistoryUi } from './store'
import { Icon } from '../components/Icon'
import { instant, kg, kg1, localParts, roundTo, shortDate, signedKg1, volume as de } from '../format'
import { apart, find, fold, isQuery, mentions } from '../search'
import { NearMisses } from '../components/NearMisses'
import { morphFrom } from '../vt'
import { useSheets } from '../session/stores'
import { useSheetHistory } from '../session/useSheetHistory'
import { PARTNER_SHEET } from '../partner/PartnerLine'
import { MitPartner, PartnerSheet } from '../partner/PartnerSheet'
import type { PartnerRef } from '../partner/types'

/** A figure never parts from its unit at a line end. */
const NB = ' '

const plural = (n: number, one: string, many: string) => `${n}${NB}${n === 1 ? one : many}`

/** "Ein Rekord ist ...": said wherever records are counted for the reader. */
const RECORD_IS = 'Ein Rekord ist ein neues geschätztes Maximum (1RM).'

/** An exercise's search text: the add sheet's, from the payload -- or its
 *  folded name, for one the payload has none for. */
const exerciseText = (payload: HistoryPayload, name: string) =>
  payload.exercise_search[name] ?? fold(name)

/** A tonnage as it is said: whole tonnes from ten, one decimal below, kilos
 *  under one tonne -- "352 Tonnen", "3,2 Tonnen", "850 kg". The bands go by
 *  the figure as printed, so 999,6 kg is never "1.000 kg" nor 9.999 kg
 *  "10,0 Tonnen". */
export function tonnes(volumeKg: number): string {
  if (roundTo(volumeKg, 0) < 1000) return `${de(volumeKg)}${NB}kg`
  if (roundTo(volumeKg / 1000, 1) < 10) return `${kg1(volumeKg / 1000)}${NB}Tonnen`
  return `${de(volumeKg / 1000)}${NB}Tonnen`
}

/** The whole history in a sentence (Statistik's lede, demoted from a
 *  headline: where no decision hangs on a number, the number is prose). */
function Lede({ summary }: { summary: HistorySummary }) {
  const one = summary.workouts === 1
  return (
    <p className="verlauf__lede">
      <b>{plural(summary.workouts, 'Workout', 'Workouts')}</b>
      {one ? ' am ' : ' seit dem '}<b>{shortDate(summary.first_at)}</b>
      {summary.tonnage > 0 && <>{', zusammen '}<b>{tonnes(summary.tonnage)}</b></>}
      {'.'}
      {/* The break still running counts: a lifter three weeks into one is
          not told about an eight-day one. */}
      {!one && summary.longest_gap >= 1 && (
        <>{' Die längste Pause: '}<b>{plural(summary.longest_gap, 'Tag', 'Tage')}</b>{'.'}</>
      )}
    </p>
  )
}

function weeksSaid(weeks: HistoryWeeks): ReactNode {
  if (weeks.weeks_trained === weeks.weeks_total) {
    return <>In <b>{`jeder der ${plural(weeks.weeks_total, 'Woche', 'Wochen')}`}</b> trainiert.</>
  }
  const head = <>In <b>{`${weeks.weeks_trained} von ${plural(weeks.weeks_total, 'Woche', 'Wochen')}`}</b> trainiert</>
  if (weeks.longest_streak < 2) return <>{head}.</>
  if (weeks.longest_streak === weeks.weeks_trained) return <>{head}, alle am Stück.</>
  return <>{head}, <b>{weeks.longest_streak}</b> davon am Stück.</>
}

/** The biggest month's bar, in px; the plot above it keeps room for the
 *  record count riding on the tallest one. */
const BAR_MAX = 60

/**
 * Statistik's career strip as the page's month index (M3): one bar per month
 * since the first workout, oldest left. Height is tonnage; the deload share
 * hatched from the foot (G-026); a month without a workout a stub, not a
 * hole; the running month an outline. The record count rides on each bar --
 * a count, not a mark, so it says something on every month. Each month jumps
 * to its band -- while it has rows to show: a month the search or the filter
 * empties is no link.
 */
function MonthIndex({ index, weeks, linked }: {
  index: HistoryIndexMonth[]
  weeks: HistoryWeeks | null
  linked: Set<string>
}) {
  const bars = useRef<HTMLOListElement>(null)
  // Which edge has months out of view: that side fades, or a strip opened at
  // its newest month, with no scrollbar, reads as the whole history (G-046).
  const [more, setMore] = useState<'' | 'start' | 'end' | 'both'>('')
  // Past about seven months the strip scrolls sideways: it opens at the
  // newest, which is what the page is read for.
  useLayoutEffect(() => {
    const el = bars.current
    if (el === null) return
    const edges = () => {
      const start = el.scrollLeft > 1
      const end = el.scrollLeft < el.scrollWidth - el.clientWidth - 1
      setMore(start && end ? 'both' : start ? 'start' : end ? 'end' : '')
    }
    el.scrollLeft = el.scrollWidth
    edges()
    el.addEventListener('scroll', edges, { passive: true })
    window.addEventListener('resize', edges)
    return () => {
      el.removeEventListener('scroll', edges)
      window.removeEventListener('resize', edges)
    }
  }, [])
  const top = Math.max(0, ...index.map((m) => m.volume))
  const hatched = index.some((m) => m.deload_volume > 0 && !m.is_current)
  const gaps = index.some((m) => m.is_gap)
  const current = index.some((m) => m.is_current)
  const records = index.some((m) => m.records > 0)

  return (
    <nav className="mindex" aria-label="Monate">
      {weeks !== null && <p className="mindex__cap">{weeksSaid(weeks)}</p>}
      <ol className="mindex__bars" ref={bars} data-more={more || undefined}>
        {index.map((m) => {
          const deload = m.deload_volume > 0 && !m.is_current
          const height = m.is_gap ? 3 : top > 0 ? Math.max(2, Math.round((m.volume / top) * BAR_MAX)) : 2
          const style: CSSProperties & Record<'--deload-share', string> = {
            blockSize: `${height}px`,
            '--deload-share': deload && m.volume > 0
              ? `${Math.round((m.deload_volume / m.volume) * 1000) / 10}%` : '0%',
          }
          const said = [
            m.is_gap ? `${m.label}: kein Workout` : `${m.label}: ${de(m.volume)} kg`,
            ...(m.records > 0 ? [plural(m.records, 'Rekord', 'Rekorde')] : []),
            ...(deload ? [`davon ${de(m.deload_volume)} kg Deload`] : []),
            ...(m.is_current ? ['läuft noch'] : []),
          ].join(', ')
          const body = (
            <>
              <span className="sr-only">{said}</span>
              <span className="mindex__plot" aria-hidden="true">
                {m.records > 0 && (
                  <span className="mindex__rec"><i className="recdot" />{m.records}</span>
                )}
                <span style={style} className={`mindex__bar${m.is_gap ? ' is-gap' : ''}${deload ? ' is-deload' : ''}${m.is_current ? ' is-current' : ''}`} />
              </span>
              {/* Each January carries its year: past twelve months the
                  strip reads "Sep … Sep" otherwise. */}
              <span className="mindex__m" aria-hidden="true">
                {m.short}{m.month === 1 && <span className="mindex__y">{` ’${String(m.year).slice(-2)}`}</span>}
              </span>
            </>
          )
          return (
            <li key={m.slug}>
              {linked.has(m.slug)
                ? <a className="mindex__mo" href={`#monat-${m.slug}`}>{body}</a>
                : <span className="mindex__mo is-off">{body}</span>}
            </li>
          )
        })}
      </ol>
      <ul className="mindex__key" aria-hidden="true">
        <li><i className="mindex__sw" />Tonnage</li>
        {hatched && <li><i className="mindex__sw mindex__sw--deload" />Deload-Anteil</li>}
        {gaps && <li><i className="mindex__sw mindex__sw--gap" />Monat ohne Workout</li>}
        {current && <li><i className="mindex__sw mindex__sw--current" />Läuft noch</li>}
        {records && <li><i className="recdot" />Rekorde</li>}
      </ul>
    </nav>
  )
}

function RecordItem({ record }: { record: HistoryRecord }) {
  const gain = signedKg1(record.e1rm - record.previous)
  return (
    <li>
      <a className="recs__item" href={`/gym/exercises/${record.exercise_id}`}
        onClick={morphFrom('ex', '.recs__name')}
        aria-label={`${record.name}: Rekord mit ${kg(record.weight)} kg × ${record.reps}, geschätztes Maximum ${kg1(record.e1rm)} kg, ${gain} kg über dem alten (${kg1(record.previous)} kg)`}>
        <span className="recs__main">
          <span className="recs__name">{record.name}</span>
          <span className="recs__meta">{`${kg(record.weight)} kg × ${record.reps} · 1RM ${kg1(record.e1rm)} kg`}</span>
        </span>
        <span className="gain">{gain}<small>kg</small></span>
      </a>
    </li>
  )
}

function Row({ entry, weekdayShort, hit, biggest, onlyRecords, onPartner }: {
  entry: HistoryEntry
  weekdayShort: string[]
  /** Whether an exercise of the row is what the search found it by; null
   *  while nothing is searched. */
  hit: ((exerciseName: string) => boolean) | null
  biggest: boolean
  /** "Nur Rekorde": the workout's records stand in for its exercise line. */
  onlyRecords: boolean
  onPartner(partner: PartnerRef): void
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
    <>
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
          {!onlyRecords && (
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
          )}
        </a>
        <span className="row__trail row__trail--stack">
          {/* .vol--none existed for this and was never applied: a session with
              no completed sets headlined a bold zero in the display face. */}
          {entry.volume
            ? <span className="vol">{de(entry.volume)}<small>kg</small></span>
            : <span className="vol vol--none">keine Sätze</span>}
          {/* A fact about its load: filled, the logged hue -- not gold, it is
              no record (D3: records are e1RM only). */}
          {biggest && <span className="vtag vtag--max">Größtes Workout</span>}
          {/* Since D3 most workouts hold a record, and a gold chip on four
              rows in five singled nothing out (G-026): the count as text
              with the record dot -- the index's and the filter's mark. */}
          {!onlyRecords && entry.record_count > 0 && (
            <span className="verlauf__rc">
              <i className="recdot" aria-hidden="true" />
              {plural(entry.record_count, 'Rekord', 'Rekorde')}
            </span>
          )}
          {/* Its own class: it borrowed vtag--neu, so restyling "Neu" would
              have silently recoloured Deload -- which must never carry a hue. */}
          {entry.is_deload && <span className="vtag vtag--deload">Deload</span>}
        </span>
        {/* Beside the row's link, not inside it: the row opens the workout,
            this opens the partner's list (D14 screen 2). */}
        {entry.partners.map((partner) => (
          <MitPartner key={partner.id} partner={partner} onOpen={onPartner} />
        ))}
      </div>
      {onlyRecords && entry.records.length > 0 && (
        <ul className="recs" aria-label={`${plural(entry.records.length, 'Rekord', 'Rekorde')} in diesem Workout`}>
          {entry.records.map((record) => <RecordItem record={record} key={record.exercise_id} />)}
        </ul>
      )}
    </>
  )
}

export function HistoryPage({ payload }: { payload: HistoryPayload }) {
  const query = useHistoryUi((s) => s.query)
  const setQuery = useHistoryUi((s) => s.setQuery)
  const onlyRecords = useHistoryUi((s) => s.onlyRecords)
  const setOnlyRecords = useHistoryUi((s) => s.setOnlyRecords)
  const exporting = useHistoryUi((s) => s.exporting)
  const startExport = useHistoryUi((s) => s.startExport)
  const cancelExport = useHistoryUi((s) => s.cancelExport)
  const selected = useHistoryUi((s) => s.selected)
  const replaceSelection = useHistoryUi((s) => s.replaceSelection)
  // "mit <Name>" opens the partner's list as it ended (D14); Back closes it
  // rather than leaving Verlauf.
  useSheetHistory()
  const openSheet = useSheets((s) => s.open)
  const [partnerShown, setPartnerShown] = useState<PartnerRef | null>(null)
  const showPartner = (partner: PartnerRef) => {
    setPartnerShown(partner)
    openSheet(PARTNER_SHEET)
  }

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

  // Search and the filter combine: the rows both let through.
  const shows = (entry: HistoryEntry) => (found === null || found.ids.has(entry.session_id))
    && (!onlyRecords || entry.record_count > 0)
  const narrowed = found !== null || onlyRecords
  // The exercises a row was found by float to the front of its line, marked.
  const hit = found === null ? null
    : (name: string) => mentions(exerciseText(payload, name), query, found.tier)

  const visible = payload.months
    .map((month) => ({ month, entries: month.entries.filter(shows) }))
    .filter(({ entries }) => entries.length > 0)
  const hitCount = visible.reduce((n, m) => n + m.entries.length, 0)
  const recordCount = visible.reduce(
    (n, m) => n + m.entries.reduce((k, e) => k + e.record_count, 0), 0)
  const linked = new Set(visible.map(({ month }) => month.slug))

  /** Presets pick from what the search is showing, never from the whole list. */
  const pickWithin = (days: number | null) => {
    const cutoff = days === null ? null : Date.now() - days * 86_400_000
    replaceSelection(visible.flatMap(({ entries }) => entries
      .filter((e) => cutoff === null || instant(e.started_at).getTime() >= cutoff)
      .map((e) => e.session_id)))
  }

  // How many rows show, said only while something narrows the list: the
  // h1's count moved here. Nothing while none shows -- the empty note says it.
  const workoutsOf = `${hitCount} von ${plural(payload.total, 'Workout', 'Workouts')}`
  const hits = hitCount === 0 ? null
    : onlyRecords
      ? <><b>{plural(recordCount, 'Rekord', 'Rekorde')}</b>{' in '}<b>{workoutsOf}</b>{`. ${RECORD_IS}`}</>
      : found !== null
        ? <><b>{workoutsOf}</b>{hitCount === 1 ? ' passt.' : ' passen.'}</>
        : null

  return (
    <>
      <header className="verlauf__head">
        <h1 className="verlauf__h">Verlauf</h1>
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
          {/* Export is a mode for picking rows: the career steps aside while
              it is on, so the first rows with their boxes are on the first
              screen. */}
          {!exporting && payload.summary !== null && <Lede summary={payload.summary} />}
          {!exporting && payload.index.length > 0 && (
            <MonthIndex index={payload.index} weeks={payload.weeks} linked={linked} />
          )}

          <div className="verlauf__find">
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
            {/* Pressed, it fills with the record hue and the dot becomes a
                tick: the state reads by shape as well as colour. */}
            <button type="button" className="verlauf__only" aria-pressed={onlyRecords}
              onClick={() => setOnlyRecords(!onlyRecords)}>
              {onlyRecords ? <Icon name="check" /> : <i className="recdot" aria-hidden="true" />}
              Nur Rekorde
            </button>
          </div>
          {/* aria-live, because search and the filter rewrite this and nothing
              else says how many rows they left. */}
          <p className="verlauf__hits" aria-live="polite">{hits}</p>

          {exporting && (
            <div className="export" id="export-panel">
              <div className="export__row">
                <span className="export__picked">{`${selected.length} ausgewählt`}</span>
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

          {hitCount === 0 && found !== null && (
            <p className="empty" role="status">
              {`Kein Workout${onlyRecords ? ' mit Rekord' : ''} gefunden für `}<b>{query.trim()}</b>.{' '}
              <button type="button" className="linklike"
                onClick={() => setQuery('')}>Suche zurücksetzen</button>
            </p>
          )}
          {hitCount === 0 && found === null && onlyRecords && (
            <p className="empty" role="status">
              {`Noch kein Rekord. ${RECORD_IS}`}{' '}
              <button type="button" className="linklike"
                onClick={() => setOnlyRecords(false)}>Alle Workouts zeigen</button>
            </p>
          )}
          {hitCount > 0 && found?.tier === 'typos' && <NearMisses query={query} />}

          <div id="verlauf-list">
            {visible.map(({ month, entries }) => (
              <section className="month-group" id={`monat-${month.slug}`} key={month.slug}
                aria-labelledby={`m-${month.slug}`}>
                <div className="month">
                  <h2 className="month__h" id={`m-${month.slug}`}>{month.label}</h2>
                  <span className="start__sp" />
                  <span className="month__n">
                    {entries.length === month.entries.length
                      ? plural(entries.length, 'Workout', 'Workouts')
                      : `${entries.length} von ${plural(month.entries.length, 'Workout', 'Workouts')}`}
                  </span>
                  {/* A month whose only sessions logged nothing has no total to
                      state, and "0 kg" under a heading reads as a bad month
                      rather than an empty one. */}
                  {month.volume > 0 && (
                    <span className="month__sum">
                      {`${de(month.volume)} kg${month.records ? ` · ${plural(month.records, 'Rekord', 'Rekorde')}` : ''}`}
                    </span>
                  )}
                </div>

                {entries.map((entry) => (
                  <div key={entry.session_id}>
                    {/* A break in training is the most important thing a
                        history can show. Only while nothing narrows the list:
                        between filtered rows a pause line dates a break to
                        the wrong workout. */}
                    {!narrowed && entry.gap_days !== null && entry.gap_days >= payload.gap_threshold && (
                      <p className="gap">{`${entry.gap_days} Tage Pause`}</p>
                    )}
                    <Row entry={entry} weekdayShort={payload.weekday_short} hit={hit}
                      biggest={entry.session_id === payload.biggest_session_id}
                      onlyRecords={onlyRecords} onPartner={showPartner} />
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
      <PartnerSheet target={partnerShown} dated />
    </>
  )
}
