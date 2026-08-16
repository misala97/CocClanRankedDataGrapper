import { useMemo, useRef, useState } from 'react'
import type {
  ProgressionRow, StatistikPayload, TimelineRecord, TonnageMonth,
} from './types'
import { kg1, roundTo, signedWhole, volume as de, whole } from '../format'
import { morphFrom } from '../vt'

/** Local time, from a naive-UTC timestamp. */
const local = (iso: string) => new Date(`${iso}Z`)
const pad = (n: number) => String(n).padStart(2, '0')
const dmy = (iso: string) => {
  const d = local(iso)
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}
const signed1 = (n: number) => `${n >= 0 ? '+' : '-'}${kg1(Math.abs(n))}`
const mmss = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`
/** "3", "3 und 4+", "2, 3 und 4+" -- German lists take no serial comma. */
const joinAnd = (parts: string[]) => (parts.length < 2
  ? parts.join('')
  : `${parts.slice(0, -1).join(', ')} und ${parts[parts.length - 1]}`)

/** The training span in years and months, or in days below a month. Months
 *  ROUND rather than floor: 58 days read "1 Monat" next to a career strip
 *  visibly spanning two. */
function span(days: number): string {
  if (days < 30) return `${days} Tage`
  let years = Math.floor(days / 365)
  let months = Math.round((days - years * 365) / 30.44)
  if (months === 12) { years += 1; months = 0 }
  const parts = []
  if (years) parts.push(`${years} ${years === 1 ? 'Jahr' : 'Jahre'}`)
  if (months) parts.push(`${months} ${months === 1 ? 'Monat' : 'Monate'}`)
  return parts.join(', ') || `${years} ${years === 1 ? 'Jahr' : 'Jahre'}`
}

function Record({ record, hit = false }: { record: TimelineRecord; hit?: boolean }) {
  // A row is in the timeline because it set at least one of the two, and the
  // weight record leads when it set both.
  const move = record.weight ?? record.e1rm!
  const unit = record.weight ? 'kg' : 'kg e1RM'
  return (
    <a className={`rec${hit ? ' is-hit' : ''}`} href={`/gym/session/${record.session_id}`}
      onClick={morphFrom('session', '.rec__name')}>
      <span className="rec__date">{dmy(record.started_at)}</span>
      <span className="rec__name">{record.name}</span>
      <span className="rec__val">
        {`${kg1(move.value)} ${unit} `}
        <small>{`vorher ${kg1(move.previous)}`}</small>
      </span>
      {record.weight !== null && record.e1rm !== null && (
        <span className="rec__also">{`auch e1RM ${kg1(record.e1rm.value)}`}</span>
      )}
    </a>
  )
}

function Progression({ entry }: { entry: ProgressionRow }) {
  return (
    <div className="prog">
      <a className="prog__name" href={`/gym/exercises/${entry.exercise_id}`}
        onClick={morphFrom('ex', null)}>
        {entry.name}
      </a>
      <span className="prog__spark">
        <svg viewBox="0 0 74 24" fill="none" aria-hidden="true">
          <polyline points={entry.spark}
            stroke={entry.is_up ? 'var(--done)' : 'var(--stall)'}
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      {/* Diverging from a centre line, so a gain and a loss are directions
          rather than two separate lists. */}
      <span className="prog__axis">
        <span className="prog__zero" />
        <span className={`prog__bar prog__bar--${entry.is_up ? 'up' : 'down'}`}
          style={{ inlineSize: `${entry.bar_pct}%` }} />
      </span>
      <span className={entry.is_up ? 'prog__pct is-up' : 'prog__pct is-down'}>
        {`${signedWhole(entry.change_pct)} %`}
      </span>
      <span className="prog__meta">
        {`${kg1(entry.first_e1rm)} → ${kg1(entry.current_e1rm)} kg`}
      </span>
    </div>
  )
}

export function StatistikPage({ payload }: { payload: StatistikPayload }) {
  // The selected stretch of the career strip, as month indices (inclusive,
  // unordered -- normalised on read). A tap is a one-month selection; a drag
  // across the bars brushes a range, and the readout under the strip
  // re-aggregates what the bars encode for it. Real buttons, so the keyboard
  // can do the tap half too.
  const [sel, setSel] = useState<[number, number] | null>(null)
  const brush = useRef<{ start: number; moved: boolean } | null>(null)
  const monthsRef = useRef<HTMLDivElement>(null)
  const {
    totals, months, progression, effort, rep_range: reps, fatigue,
    daypart, weekday, rest_gap: restGap, rest_habit: restHabit,
    session_length: length, consistency, balance_drift: drift,
    increment_ladder: ladder, record_drought: drought,
  } = payload

  const selRange: [number, number] | null = sel === null
    ? null
    : [Math.min(sel[0], sel[1]), Math.max(sel[0], sel[1])]
  const selMonths: TonnageMonth[] = selRange === null
    ? []
    : months.slice(selRange[0], selRange[1] + 1)
  const selKeys = useMemo(
    () => new Set(selMonths.map((m) => `${m.year}-${m.month}`)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sel, months])

  // UTC getters, matching the server's month bucketing -- local time would
  // shift a record logged near midnight into the neighbouring month's bar.
  const recordKey = (record: TimelineRecord) => {
    const d = new Date(`${record.started_at}Z`)
    return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}`
  }
  const allRecords = useMemo(
    () => [...payload.recent_records, ...payload.record_years.flatMap((b) => b.records)],
    [payload])
  const recordsInSel = sel === null ? 0
    : allRecords.filter((r) => selKeys.has(recordKey(r))).length

  const monthIndexFromX = (clientX: number) => {
    const el = monthsRef.current
    if (el === null || months.length === 0) return 0
    const box = el.getBoundingClientRect()
    if (box.width === 0) return 0
    const i = Math.floor(((clientX - box.left) / box.width) * months.length)
    return Math.max(0, Math.min(months.length - 1, i))
  }

  // The bar actually pressed, when the press landed on one. Preferred over the
  // x-arithmetic above because it cannot disagree with what the finger or
  // cursor was on: the bars carry gaps between them, and a press in a gap
  // should belong to the bar it hit, not to the slice of the strip's width it
  // fell in. Null for a press on the strip's own background, which the drag
  // path resolves by x.
  const monthIndexFromTarget = (target: EventTarget | null) => {
    const strip = monthsRef.current
    const bar = target instanceof Element ? target.closest('.mo') : null
    if (strip === null || bar === null) return null
    const i = [...strip.children].indexOf(bar)
    return i < 0 ? null : i
  }

  const toggleMonth = (i: number) =>
    setSel(sel !== null && sel[0] === i && sel[1] === i ? null : [i, i])

  if (totals.sessions === 0) {
    return (
      <p className="empty">
        Noch keine abgeschlossenen Workouts — hier steht die ganze Laufbahn,
        sobald es eine gibt.
      </p>
    )
  }

  const peak = Math.max(...months.map((m) => m.volume), 0) || 1
  // Deduped by INDEX, not by rendered text: at two months the midpoint IS the
  // last month, so first/middle/last printed the same label twice side by side.
  const tickIx = [...new Set([0, Math.floor(months.length / 2), months.length - 1])]
    .filter((i) => i >= 0 && i < months.length)

  // Every group, never a top-6: truncating dropped a group from the bar AND
  // the key, so the shares silently stopped summing to 100. The ramp floors at
  // 0.7 -- measured, 0.55 fell to 2.48:1 contrast against the panel.
  const fade = effort.groups.length > 1 ? 0.3 / effort.groups.length : 0
  const topExercises = effort.exercises.slice(0, 5)
  const widest = topExercises[0]?.volume ?? 1

  const topShare = Math.max(...reps.buckets.map((b) => b.share), 0)
  // Only the drawn buckets, and the ceiling comes from them too: a bucket that
  // is hidden for having too few workouts must not set the scale every visible
  // bar is measured against.
  const shownGaps = restGap.buckets.filter((b) => b.shown)
  const peakGap = Math.max(...shownGaps.map((b) => b.avg_volume), 0)
  const bestPart = daypart.statable
    ? daypart.parts.reduce((a, b) => (b.volume >= a.volume ? b : a))
    : null
  // The most PRODUCTIVE day, which is only worth naming when it is not also
  // the most frequent one -- otherwise the sentence says the same thing twice.
  const heaviestDay = weekday.statable
    ? weekday.days.reduce((a, b) => (b.avg_volume >= a.avg_volume ? b : a))
    : null
  const topDrift = drift.groups[0] ?? null
  const bottomDrift = drift.groups[drift.groups.length - 1] ?? null
  const topRungs = ladder.exercises.filter((e) => e.notches > 0).slice(0, 5)
  const widestRung = topRungs[0]?.notches ?? 1
  const stalest = drought.exercises.slice(0, 4)
  const bestDay = weekday.statable
    ? weekday.days.reduce((a, b) => (b.share >= a.share ? b : a))
    : null

  const perWeek = totals.days_training !== null && totals.days_training >= 7
    ? kg1(totals.sessions / (totals.days_training / 7))
    : '—'

  return (
    <>
      <section className="lede" aria-labelledby="lede-h">
        <span className="lede__main">
          <span className="lede__kick">
            {`Seit ${dmy(totals.first_session!)} · ${span(totals.days_training!)}`}
          </span>
          <h1 className="lede__h" id="lede-h">
            Du hast <em>{`${de(totals.tonnage / 1000)} Tonnen`}</em> bewegt
            {payload.longest_gap
              ? ` und dabei nie länger als ${payload.longest_gap} Tage pausiert.`
              : '.'}
          </h1>
        </span>
        <span className="lede__aside">
          {/* Tonnage is a number nobody can feel. An elephant is roughly six
              tonnes, which is the only unit here anyone has a picture of. */}
          {`≈ ${whole(totals.tonnage / 6000)} ausgewachsene Elefanten`}<br />
          {totals.best_session !== null && (
            <>
              Größtes Workout:{' '}
              <a href={`/gym/session/${totals.best_session.session_id}`}>
                <b>{`${de(totals.best_session.volume)} kg`}</b>
              </a>
              {` · ${dmy(totals.best_session.started_at)}`}
            </>
          )}
        </span>
      </section>

      <div className="totals">
        <span className="total">
          <span className="total__v">{totals.sessions}</span>
          <span className="label">Workouts</span>
        </span>
        <span className="total">
          <span className="total__v">{de(totals.sets)}</span>
          <span className="label">Sätze</span>
        </span>
        <span className="total">
          <span className="total__v">{de(totals.reps)}</span>
          <span className="label">Wiederholungen</span>
        </span>
        <span className="total">
          <span className="total__v">{de(totals.tonnage / 1000)}<small>t</small></span>
          <span className="label">Tonnage</span>
        </span>
        <span className="total">
          <span className="total__v">{perWeek}<small>/Wo.</small></span>
          <span className="label">Schnitt</span>
        </span>
        {/* Regularity, which every other tile here is blind to: five tonnage
            figures cannot tell a steady month from a heavy fortnight followed
            by nothing. */}
        {consistency.statable && (
          <span className="total">
            <span className="total__v">{consistency.current_streak}<small>Wo.</small></span>
            <span className="label">Serie</span>
          </span>
        )}
      </div>

      {months.length > 0 && (
        <section className="career" aria-labelledby="career-h">
          <div className="sec__head">
            <h2 className="label" id="career-h">Die ganze Laufbahn</h2>
            <span className="sec__sp" />
            <span className="label">Ein Balken je Monat · Höhe = Tonnage</span>
          </div>
          <div className="career__body">
            {/* A list, not role="img". role="img" tells assistive tech to
                ignore every child, so the per-bar titles were unreachable in
                principle and the flagship figure conveyed exactly one fact:
                that it existed. title= stays for the mouse. */}
            <div className="months" role="list" ref={monthsRef}
              aria-label={`Monatliche Tonnage seit ${payload.month_names[months[0]!.month - 1]} ${months[0]!.year}`}
              onPointerDown={(e) => {
                brush.current = {
                  start: monthIndexFromTarget(e.target) ?? monthIndexFromX(e.clientX),
                  moved: false,
                }
                try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* jsdom */ }
              }}
              onPointerMove={(e) => {
                const b = brush.current
                if (b === null) return
                const i = monthIndexFromX(e.clientX)
                if (i !== b.start) b.moved = true
                if (b.moved) setSel([b.start, i])
              }}
              onPointerUp={() => {
                const b = brush.current
                brush.current = null
                // A press that never moved is a tap, and it is answered HERE
                // rather than by the bar's onClick: setPointerCapture above
                // retargets a captured pointer's click to this container, so
                // with a mouse the bar's own click never fires. Touch delivers
                // it to the bar anyway -- which is why this was invisible on a
                // phone and dead on a desktop. The click, whichever way it is
                // targeted, is ignored below.
                if (b !== null && !b.moved) toggleMonth(b.start)
              }}
              onPointerCancel={() => { brush.current = null }}>
              {months.map((m, i) => {
                // The strip's right edge is not a collapse: the running month
                // says it is still filling. The LAST month is the running one
                // by construction -- analytics builds the strip through now --
                // so no clock is consulted (a clock check would flip the
                // month-boundary render).
                const isCurrent = i === months.length - 1 && !m.is_gap
                const label = `${payload.month_names[m.month - 1]} ${m.year}: ${de(m.volume)} kg`
                  + (m.has_record ? ', Rekordmonat' : '')
                  + (m.has_deload ? ', Deload' : '')
                  + (m.is_gap ? ', kein Workout' : '')
                  + (isCurrent ? ', läuft noch' : '')
                const key = `${m.year}-${m.month}`
                return (
                  /* A real button (keyboard + focus), inside the pointer-brush
                     container: every pointer selection is handled above, so
                     the button's own click only acts for the keyboard, which
                     is the one caller that raises no pointer at all (detail 0
                     -- Enter and Space synthesise a clickless click). */
                  <button type="button" key={key} role="listitem"
                    className={`mo${m.has_record ? ' is-record' : ''}${m.has_deload ? ' is-deload' : ''}${m.is_gap ? ' is-gap' : ''}${isCurrent ? ' is-current' : ''}${selKeys.has(key) ? ' is-picked' : ''}`}
                    aria-label={label} title={label}
                    aria-pressed={selKeys.has(key)}
                    onClick={(e) => {
                      if (e.detail !== 0) return
                      toggleMonth(i)
                    }}
                    style={{ blockSize: `${m.is_gap ? 2 : roundTo((m.volume / peak) * 100, 1)}%` }} />
                )
              })}
            </div>
            <div className="months__axis">
              {tickIx.map((i) => (
                <span className="label" key={i}>
                  {`${payload.month_names[months[i]!.month - 1]!.slice(0, 3)} ${months[i]!.year}`}
                </span>
              ))}
            </div>
            {/* The selection, in words. One bar reads as before; a brushed
                range re-aggregates what the bars encode -- tonnage, record
                months, and (from the timeline below) the records inside it. */}
            <p className="chart__read">
              {(() => {
                if (selMonths.length === 0) {
                  return <span className="chart__hint">Balken antippen — oder ziehen für einen Zeitraum</span>
                }
                if (selMonths.length === 1) {
                  const m = selMonths[0]!
                  return (
                    <>
                      {`${payload.month_names[m.month - 1]} ${m.year} · `}
                      <b>{`${de(m.volume)} kg`}</b>
                      {m.has_record && <span className="chart__read-tag vtag vtag--record">Rekordmonat</span>}
                      {m.has_deload && <span className="chart__read-tag vtag vtag--deload">Deload</span>}
                      {m.is_gap && ' · kein Workout'}
                    </>
                  )
                }
                const first = selMonths[0]!
                const last = selMonths[selMonths.length - 1]!
                const sum = selMonths.reduce((a, m) => a + m.volume, 0)
                const recordMonths = selMonths.filter((m) => m.has_record).length
                return (
                  <>
                    {`${payload.month_names[first.month - 1]} ${first.year} – ${payload.month_names[last.month - 1]} ${last.year}`}
                    {` · ${selMonths.length} Monate · `}
                    <b>{`${de(sum)} kg`}</b>
                    {recordMonths > 0 && ` · ${recordMonths} ${recordMonths === 1 ? 'Rekordmonat' : 'Rekordmonate'}`}
                    {recordsInSel > 0 && ` · ${recordsInSel} ${recordsInSel === 1 ? 'Rekord' : 'Rekorde'} unten markiert`}
                  </>
                )
              })()}
            </p>
            {/* Each swatch is drawn the way its mark is drawn -- the deload key
                was a solid square standing for a hatch. */}
            <div className="chart__legend">
              <span className="key">
                <span className="key__dot key__dot--sq" style={{ background: 'var(--done)' }} />
                Tonnage
              </span>
              <span className="key">
                <span className="key__dot key__dot--sq key__dot--record" />Monat mit Rekord
              </span>
              <span className="key">
                <span className="key__dot key__dot--sq key__dot--deload" />Deload-Monat
              </span>
              <span className="key">
                {/* Not "Pause": on this page that word is already the gap
                    between workouts and the rest between sets. */}
                <span className="key__dot key__dot--sq key__dot--gap" />Monat ohne Workout
              </span>
              <span className="key">
                <span className="key__dot key__dot--sq key__dot--current" />Läuft noch
              </span>
            </div>
            {/* The strip is months of tonnage; this is the same span counted
                in weeks that held a workout at all. A quiet line rather than
                a figure of its own: it qualifies the strip above it. */}
            {consistency.statable && (
              <p className="label">
                {`In ${consistency.weeks_trained} von ${consistency.weeks_total} Wochen trainiert`}
                {consistency.longest_streak > consistency.current_streak
                  && ` · längste Serie ${consistency.longest_streak} Wochen`}
              </p>
            )}
          </div>
        </section>
      )}

      <div className="stat-cols">
        <div className="stat-col">
          <section aria-labelledby="prog-h">
            <div className="sec__head">
              <h2 className="label" id="prog-h">Fortschritt seit dem ersten Mal</h2>
              <span className="sec__sp" />
              <span className="label">e1RM, erste gegen aktuelle Einheit</span>
            </div>
            {progression.length > 0 ? (
              progression.map((entry) => (
                <Progression entry={entry} key={entry.exercise_id} />
              ))
            ) : (
              <p className="empty">Noch zu wenig Historie, um Fortschritt zu messen.</p>
            )}
          </section>

          <section aria-labelledby="effort-h">
            <div className="sec__head">
              <h2 className="label" id="effort-h">Wohin die Arbeit geht</h2>
              <span className="sec__sp" />
              {/* Not "Anteil an 175 t": that made the third restatement of the
                  same tonnage inside 400px, and by the third time the headline
                  number stops reading as a finding. */}
              <span className="label">Anteil am Gesamtvolumen</span>
            </div>
            {effort.groups.length > 0 ? (
              <>
                {/* Every second segment hatched: at five groups the opacity
                    ramp alone stepped by ~0.06, which made the last three
                    segments (and their key swatches) indistinguishable. The
                    hatch is a second carrier the ramp keeps failing to be. */}
                <div className="stack-bar">
                  {effort.groups.map((group, i) => (
                    <span key={group.label}
                      className={i % 2 === 1 ? 'is-hatched' : undefined}
                      style={{
                        inlineSize: `${roundTo(group.share, 1)}%`,
                        background: 'var(--done)',
                        opacity: roundTo(1 - i * fade, 3),
                      }} />
                  ))}
                </div>
                <div className="stack-key">
                  {effort.groups.map((group, i) => (
                    <span className="key" key={group.label}>
                      <span className={`key__dot key__dot--sq${i % 2 === 1 ? ' is-hatched' : ''}`}
                        style={{
                          background: 'var(--done)',
                          opacity: roundTo(1 - i * fade, 3),
                        }} />
                      {` ${group.label} ${whole(group.share)} %`}
                    </span>
                  ))}
                </div>
                {topExercises.map((item) => (
                  <div className="prog prog--plain" key={item.label}>
                    <span className="prog__name">{item.label}</span>
                    <span className="prog__axis">
                      <span className="prog__bar prog__bar--flat"
                        style={{ inlineSize: `${roundTo((item.volume / widest) * 100, 1)}%` }} />
                    </span>
                    <span className="prog__pct">{`${de(item.volume / 1000)} t`}</span>
                  </div>
                ))}
              </>
            ) : (
              <p className="empty">Noch keine Sätze protokolliert.</p>
            )}
          </section>

          {/* The split above is all-time, which is exactly why it cannot show
              this: a muscle group neglected for a month still carries its
              lifetime share. Shares on both sides, never tonnage -- a lighter
              month would otherwise read as abandoning every group at once. */}
          <section aria-labelledby="drift-h">
            <div className="sec__head">
              <h2 className="label" id="drift-h">Was sich zuletzt verschoben hat</h2>
              <span className="sec__sp" />
              <span className="label">{`Letzte ${drift.window_days} Tage gegen davor`}</span>
            </div>
            {drift.statable && topDrift !== null && bottomDrift !== null ? (
              <>
                {drift.groups.map((group) => (
                  <div className="prog prog--plain" key={group.label ?? 'ohne'}>
                    <span className="prog__name">{group.label ?? 'Ohne Gruppe'}</span>
                    <span className="prog__axis">
                      <span className="prog__bar prog__bar--flat"
                        style={{
                          inlineSize: `${roundTo((Math.abs(group.delta)
                            / Math.max(Math.abs(topDrift.delta), Math.abs(bottomDrift.delta), 1)) * 100, 1)}%`,
                        }} />
                    </span>
                    <span className="prog__pct"
                      title={`${whole(group.earlier_share)} % → ${whole(group.recent_share)} %`}>
                      {`${signed1(group.delta)} %`}
                    </span>
                  </div>
                ))}
                <p className="sec__note">
                  {`Aus ${drift.recent_sessions} Workouts zuletzt gegen ${drift.earlier_sessions} davor.`}
                </p>
              </>
            ) : (
              <p className="empty">
                Noch kein Davor zum Vergleichen — dafür braucht es Workouts vor
                den letzten {drift.window_days} Tagen.
              </p>
            )}
          </section>
        </div>

        {/* The narrow column: prose answers first, then the two rankings that
            are a name and a number. They sit here rather than beside the wide
            figures because of what they ARE, not to balance the height -- a
            list of "Bankdrücken · 5" needs no width, while the bar charts to
            the left are unreadable without it. */}
        <div className="stat-col">
        <section aria-labelledby="read-h">
          <div className="sec__head"><h2 className="label" id="read-h">Wie du trainierst</h2></div>

          <div className="read">
            <p className="read__q">In welchem Wiederholungsbereich?</p>
            {reps.statable && reps.dominant !== null ? (
              <>
                <p className="read__a">Meist zwischen <em>{reps.dominant.label}</em> Wdh.</p>
                <div className="read__bars" role="list">
                  {reps.buckets.map((bucket) => (
                    /* The share exists only as bar height, so it is stated as
                       text too -- the label alone named the buckets without
                       saying how much sat in any of them. */
                    <span className="rb" role="listitem" key={bucket.label}
                      aria-label={`${bucket.label} Wdh.: ${whole(bucket.share)} Prozent${bucket.label === reps.dominant!.label ? ', am häufigsten' : ''}`}>
                      <span className="rb__track">
                        <span className={bucket.label === reps.dominant!.label
                          ? 'rb__fill is-top' : 'rb__fill'}
                          style={{ blockSize: `${topShare ? roundTo((bucket.share / topShare) * 100, 1) : 0}%` }} />
                      </span>
                      <span className="rb__lbl" aria-hidden="true">{bucket.label}</span>
                    </span>
                  ))}
                </div>
                <p className="read__silent">{`Aus ${de(reps.sample)} Sätzen.`}</p>
              </>
            ) : (
              <p className="read__silent">
                {`Noch nicht genug Sätze — dafür braucht es mindestens ${payload.min_sets_for_rep_range}. Die Frage bleibt offen, statt geraten zu werden.`}
              </p>
            )}
          </div>

          <div className="read">
            <p className="read__q">Was passiert innerhalb einer Übung?</p>
            {fatigue.statable ? (
              <>
                <p className="read__a">
                  Satz 1 bis letzter Satz:{' '}
                  <em>{`${signed1(fatigue.last_reps! - fatigue.first_reps!)} Wdh.`}</em>
                </p>
                <p className="read__silent">
                  {`Bei ${signed1(fatigue.weight_change_pct!)} % Gewichtsänderung. Aus ${de(fatigue.sample)} Einheiten.`}
                </p>
              </>
            ) : (
              <p className="read__silent">Noch nicht genug Einheiten mit mehreren Sätzen.</p>
            )}
          </div>

          <div className="read">
            <p className="read__q">Wann trainierst du?</p>
            {daypart.statable || weekday.statable ? (
              <>
                <p className="read__a">
                  {bestPart !== null
                    && (payload.daypart_names[bestPart.label] ?? bestPart.label)}
                  {bestPart !== null && bestDay !== null && ', am liebsten '}
                  {bestDay !== null && <em>{`${payload.weekday_names[bestDay.weekday]}s`}</em>}
                </p>
                <p className="read__silent">
                  {bestDay !== null
                    && `${payload.weekday_names[bestDay.weekday]} ist mit ${whole(bestDay.share)} % der häufigste Tag. `}
                  {/* Frequency and productivity are different questions, and
                      the answer is only worth a sentence when they disagree. */}
                  {heaviestDay !== null && bestDay !== null
                    && heaviestDay.weekday !== bestDay.weekday
                    && `Am meisten bewegst du ${payload.weekday_names[heaviestDay.weekday]}s, im Schnitt ${de(heaviestDay.avg_volume)} kg. `}
                  {weekday.statable && `Aus ${weekday.sample} Workouts.`}
                </p>
              </>
            ) : (
              <p className="read__silent">Noch nicht genug Workouts, um ein Muster zu behaupten.</p>
            )}
          </div>

          {/* The one question the page could never answer: the strip counts
              months, the gap card counts days off, and nothing counted the
              hour itself. Median, because the stamps are written by a human
              pressing a button and the tail is made of forgetting. */}
          <div className="read">
            <p className="read__q">Wie lange dauert ein Workout?</p>
            {length.statable ? (
              <>
                <p className="read__a">
                  <em>{`${length.median_minutes} Minuten`}</em>
                  {length.volume_per_minute !== null
                    && <>, rund <em>{`${de(length.volume_per_minute)} kg`}</em> pro Minute</>}
                </p>
                <p className="read__silent">
                  {`Aus ${length.sample} gestoppten Workouts.`}
                  {length.untimed > 0
                    && ` ${length.untimed} weitere liefen ohne Schlusszeit und zählen hier nicht mit.`}
                </p>
              </>
            ) : (
              <p className="read__silent">
                Noch zu wenige Workouts mit Start- und Schlusszeit.
              </p>
            )}
          </div>

          {/* "Pause" means two different things on this page -- the days
              between two workouts, and the seconds between two sets. Both
              questions used to open with the bare word, so which one was being
              answered depended on reading the caption. Each now names its own
              unit in the question itself. */}
          <div className="read">
            <p className="read__q">Bringt mehr Zeit zwischen zwei Workouts mehr Leistung?</p>
            {restGap.statable ? (
              <>
                <div className="read__bars" role="list">
                  {shownGaps.map((bucket) => (
                    <span className="rb" role="listitem" key={bucket.label}
                      aria-label={`${bucket.label} Tage seit dem letzten Workout: Ø ${de(bucket.avg_volume)} kg`}>
                      <span className="rb__track">
                        <span className="rb__fill"
                          style={{ blockSize: `${peakGap ? roundTo((bucket.avg_volume / peakGap) * 100, 1) : 0}%` }} />
                      </span>
                      <span className="rb__lbl" aria-hidden="true">{`${bucket.label} T.`}</span>
                    </span>
                  ))}
                </div>
                <p className="read__silent">
                  {'Ø Volumen eines Workouts, nach Tagen seit dem letzten.'}
                  {restGap.thin.length > 0
                    && ` Für ${joinAnd(restGap.thin.map((b) => b.label))} Tage fehlen noch Workouts.`}
                </p>
              </>
            ) : (
              <p className="read__silent">
                Noch nicht genug Daten — dafür braucht es mehrere Workouts pro
                Abstand. Die Frage bleibt offen, statt geraten zu werden.
              </p>
            )}
          </div>

          {/* Measured against planned. Absent entirely before any session was
              logged with timestamps -- an unanswerable question reads as a
              broken feature, not as an empty one. The whole block including
              its wrapping div is gated: `.read + .read` paints a rule and a
              gap from the div's mere presence. */}
          {restHabit !== null && (
            <div className="read">
              <p className="read__q">Wie lange pausierst du zwischen zwei Sätzen?</p>
              <p className="read__a">
                Geplant <em>{mmss(restHabit[0])}</em>,
                genommen <em>{mmss(restHabit[1])}</em>.
              </p>
            </div>
          )}
        </section>

        {/* Progress in the units the gym actually offers. A percentage is the
            honest general answer; the next pin hole is the one you can act on,
            and on an uneven stack the two are not the same fact. */}
        {topRungs.length > 0 && (
          <section aria-labelledby="ladder-h">
            <div className="sec__head">
              <h2 className="label" id="ladder-h">Stufen erklommen</h2>
              <span className="sec__sp" />
              <span className="label">{`${ladder.total_notches} insgesamt`}</span>
            </div>
            {topRungs.map((rung) => (
              <div className="prog prog--plain prog--count" key={rung.exercise_id}>
                <span className="prog__name">{rung.name}</span>
                <span className="prog__axis">
                  <span className="prog__bar prog__bar--flat"
                    style={{ inlineSize: `${roundTo((rung.notches / widestRung) * 100, 1)}%` }} />
                </span>
                <span className="prog__pct"
                  title={`${de(rung.from_weight)} → ${de(rung.to_weight)} kg`}>
                  {`${rung.notches}×`}
                </span>
              </div>
            ))}
            <p className="sec__note">In Schritten dieser Geräte, nicht in Prozent.</p>
          </section>
        )}

        {/* The other half of the progression ranking in the wide column: which
            lift has gone longest without beating itself. Counted in sessions,
            not days -- a lift trained twice a month has not stalled as hard as
            one trained twice a week after the same four weeks. */}
        {stalest.length > 0 && (
          <section aria-labelledby="drought-h">
            <div className="sec__head">
              <h2 className="label" id="drought-h">Am längsten ohne Bestwert</h2>
              <span className="sec__sp" />
              <span className="label">Einheiten</span>
            </div>
            {stalest.map((row) => (
              <div className="prog prog--plain prog--count" key={row.exercise_id}>
                <span className="prog__name">{row.name}</span>
                <span className="prog__axis">
                  <span className="prog__bar prog__bar--flat"
                    style={{
                      inlineSize: `${roundTo((row.sessions_since / (stalest[0]!.sessions_since || 1)) * 100, 1)}%`,
                    }} />
                </span>
                <span className="prog__pct"
                  title={row.last_record_at === null
                    ? 'Noch nie über die erste Einheit hinaus'
                    : `Letzter Rekord: ${dmy(row.last_record_at)}`}>
                  {`${row.sessions_since}`}
                </span>
              </div>
            ))}
          </section>
        )}
        </div>
      </div>

      {/* One row per exercise-day, carrying whichever bests it set. The recent
          ones are flat and everything older folds into year bands, because
          bounding by CALENDAR did nothing for a history that fits inside one
          year: one band, forced open, holding every record there was. */}
      {payload.recent_records.length > 0 && (
        <section className="career" aria-labelledby="rec-h">
          <div className="sec__head">
            <h2 className="label" id="rec-h">Jeder Rekord</h2>
            <span className="sec__sp" />
            <span className="label">{`${payload.records_total} insgesamt`}</span>
          </div>

          {payload.recent_records.map((record) => (
            <Record record={record} key={`${record.session_id}-${record.exercise_id}`}
              hit={selKeys.has(recordKey(record))} />
          ))}

          {payload.record_years.map((band) => (
            /* A band with brushed records inside opens itself: a highlight
               nobody can see is not a highlight. */
            <details className="year" key={band.year}
              open={band.records.some((r) => selKeys.has(recordKey(r))) || undefined}>
              <summary className="year__head">
                <svg className="group__chev" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                  strokeLinejoin="round" aria-hidden="true">
                  <path d="M9 5l7 7-7 7" />
                </svg>
                <span className="label">{band.year}</span>
                <span className="sec__sp" />
                {/* "weitere", not "Rekorde": the recent rows above are usually
                    the same year, so "2026 · 31 Rekorde" under twelve more
                    2026 records reads as a contradiction. */}
                <span className="label">{`${band.records.length} weitere`}</span>
              </summary>
              {band.records.map((record) => (
                <Record record={record} key={`${record.session_id}-${record.exercise_id}`}
                  hit={selKeys.has(recordKey(record))} />
              ))}
            </details>
          ))}
        </section>
      )}
    </>
  )
}
