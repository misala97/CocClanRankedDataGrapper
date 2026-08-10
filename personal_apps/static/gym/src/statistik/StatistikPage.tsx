import type {
  ProgressionRow, StatistikPayload, TimelineRecord,
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

/** The training span in whole years and months, or in days below a month. */
function span(days: number): string {
  const years = Math.floor(days / 365)
  const months = Math.floor((days % 365) / 30)
  if (!years && !months) return `${days} Tage`
  const parts = []
  if (years) parts.push(`${years} ${years === 1 ? 'Jahr' : 'Jahre'}`)
  if (months) parts.push(`${months} ${months === 1 ? 'Monat' : 'Monate'}`)
  return parts.join(', ')
}

function Record({ record }: { record: TimelineRecord }) {
  // A row is in the timeline because it set at least one of the two, and the
  // weight record leads when it set both.
  const move = record.weight ?? record.e1rm!
  const unit = record.weight ? 'kg' : 'kg e1RM'
  return (
    <a className="rec" href={`/gym/session/${record.session_id}`}
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
  const {
    totals, months, progression, effort, rep_range: reps, fatigue,
    daypart, weekday, rest_gap: restGap, rest_habit: restHabit,
  } = payload

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
  const peakGap = Math.max(...restGap.buckets.map((b) => b.avg_volume), 0)
  const bestPart = daypart.statable
    ? daypart.parts.reduce((a, b) => (b.volume >= a.volume ? b : a))
    : null
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
            <div className="months" role="list"
              aria-label={`Monatliche Tonnage seit ${payload.month_names[months[0]!.month - 1]} ${months[0]!.year}`}>
              {months.map((m) => {
                const label = `${payload.month_names[m.month - 1]} ${m.year}: ${de(m.volume)} kg`
                  + (m.has_record ? ', Rekordmonat' : '')
                  + (m.has_deload ? ', Deload' : '')
                  + (m.is_gap ? ', keine Einheit' : '')
                return (
                  <span key={`${m.year}-${m.month}`} role="listitem"
                    className={`mo${m.has_record ? ' is-record' : ''}${m.has_deload ? ' is-deload' : ''}${m.is_gap ? ' is-gap' : ''}`}
                    aria-label={label} title={label}
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
                <span className="key__dot key__dot--sq key__dot--gap" />Pause
              </span>
            </div>
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

          <section style={{ marginTop: 'var(--sp-8)' }} aria-labelledby="effort-h">
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
                <div className="stack-bar">
                  {effort.groups.map((group, i) => (
                    <span key={group.label} style={{
                      inlineSize: `${roundTo(group.share, 1)}%`,
                      background: 'var(--done)',
                      opacity: roundTo(1 - i * fade, 3),
                    }} />
                  ))}
                </div>
                <div className="stack-key">
                  {effort.groups.map((group, i) => (
                    <span className="key" key={group.label}>
                      <span className="key__dot key__dot--sq" style={{
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
        </div>

        {/* Every zone that cannot answer says so. The silence rule is the
            point: a question shown as open is information, a question quietly
            dropped is not. */}
        <section className="stat-col" aria-labelledby="read-h">
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
                  {weekday.statable && `Aus ${weekday.sample} Workouts.`}
                </p>
              </>
            ) : (
              <p className="read__silent">Noch nicht genug Workouts, um ein Muster zu behaupten.</p>
            )}
          </div>

          <div className="read">
            <p className="read__q">Bringt mehr Pause mehr Leistung?</p>
            {restGap.statable ? (
              <>
                <div className="read__bars" role="list">
                  {restGap.buckets.map((bucket) => (
                    <span className="rb" role="listitem" key={bucket.label}
                      aria-label={`${bucket.label} Tage Abstand: Ø ${de(bucket.avg_volume)} kg`}>
                      <span className="rb__track">
                        <span className="rb__fill"
                          style={{ blockSize: `${peakGap ? roundTo((bucket.avg_volume / peakGap) * 100, 1) : 0}%` }} />
                      </span>
                      <span className="rb__lbl" aria-hidden="true">{`${bucket.label} T.`}</span>
                    </span>
                  ))}
                </div>
                <p className="read__silent">Ø Volumen je Abstand in Tagen.</p>
              </>
            ) : (
              <p className="read__silent">
                Noch nicht genug Daten — dafür braucht es mehrere Workouts je
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
              <p className="read__q">Wie lange pausierst du?</p>
              <p className="read__a">
                Du planst <em>{mmss(restHabit[0])}</em>,
                nimmst dir <em>{mmss(restHabit[1])}</em>.
              </p>
            </div>
          )}
        </section>
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
            <Record record={record} key={`${record.session_id}-${record.exercise_id}`} />
          ))}

          {payload.record_years.map((band) => (
            <details className="year" key={band.year}>
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
                <Record record={record} key={`${record.session_id}-${record.exercise_id}`} />
              ))}
            </details>
          ))}
        </section>
      )}
    </>
  )
}
