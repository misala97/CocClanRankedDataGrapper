import { useState, type CSSProperties } from 'react'
import type { ChartGeometry, ChartPoint } from '../types'
import { kg1, shortDate } from '../format'

interface Props {
  chart: ChartGeometry
  sessionCount: number
  firstDate: string
  lastDate: string
}

/**
 * Inline SVG, not a canvas. It inherits the palette directly -- a canvas can
 * only read a resolved rgb(), so a themed canvas silently loses its colours,
 * which this project has been bitten by once already. It also keeps a 208 KB
 * charting dependency off a page that draws one line per slot.
 *
 * One group per slot. Opacity, not hue: the palette is fixed at three semantic
 * hues and a slot number is not a state, so the slot with the most sessions
 * draws solid and occasional ones recede.
 *
 * A deload is a real point but not a real trend, so its legs are dotted and
 * grey -- a solid line through a deliberately light week reads as a collapse
 * that never happened.
 */
export function ExerciseChart({ chart, sessionCount, firstDate, lastDate }: Props) {
  // The tapped point, as (series position, point index). Pointer-only on
  // purpose: the log below the chart carries every plotted value, so keyboard
  // and screen-reader users already have a first-class path to the numbers --
  // the SVG stays role="img", which tells assistive tech to read its label
  // and skip the internals, and focusable children inside it would contradict
  // that. See the a11y note on the readout below.
  const [picked, setPicked] = useState<{ position: number; index: number } | null>(null)
  const width = Math.trunc(chart.width)
  const height = Math.trunc(chart.height)
  const mid = Math.trunc(chart.height / 2)
  const bottom = height - 10

  const description =
    `Verlauf des e1RM über ${sessionCount} Einheiten, ` +
    `${firstDate} bis ${lastDate}. ` +
    `Zwischen ${kg1(chart.lo)} und ${kg1(chart.hi)} Kilogramm. ` +
    `Die Tabelle darunter enthält dieselben Werte.`

  return (
    <div className="chart">
      {/* The y labels are HTML, not SVG text: the SVG is stretched to the
          container, so anything inside it scales with the drawing and would
          read at a different size on every screen. Placed by percentage
          against the same viewBox fractions the gridlines use. */}
      <div className="chart__y" aria-hidden="true">
        {chart.ticks.map((tick) => (
          <span className="label" key={tick.text} style={{ top: `${tick.y_pct}%` }}>
            {tick.text}
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={description}>
        <g stroke="var(--edge)" strokeWidth="1">
          <line x1="0" y1="10" x2={width} y2="10" />
          <line x1="0" y1={mid} x2={width} y2={mid} />
          <line x1="0" y1={bottom} x2={width} y2={bottom} />
        </g>

        {/* One wrapper around every drawn series, so the whole plot wipes in as
            a single left-to-right gesture -- along the axis it is drawn on,
            which is time. The gridlines stay put: they are the frame, not the
            report. See the MOTION note in this section of gym.css. */}
        <g className="chart__ink">
          {chart.series.map((entry) => (
            <g opacity={entry.opacity} key={entry.position}>
              {entry.points.slice(0, -1).map((a, i) => {
                const b = entry.points[i + 1]!
                const touchesDeload = a.is_deload || b.is_deload
                return (
                  <line
                    key={`seg-${i}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={touchesDeload ? 'var(--unlit)' : 'var(--done)'}
                    strokeWidth={entry.width}
                    strokeLinecap="round"
                    {...(touchesDeload ? { strokeDasharray: '3 4' } : {})}
                  />
                )
              })}

              {entry.points.map((point, i) => (
                /* The record dot is ringed. Gold on the light panel measures
                   1,86:1 -- the weakest mark on the chart -- and a ring in
                   --done (7,29:1) gives the shape a readable edge without
                   giving up the gold that means "record" everywhere else.

                   Deload dots are HOLLOW rather than filled: --unlit is an ink,
                   and filling with it made the deload the darkest mark on a
                   chart where it is meant to be the quietest. Recessiveness
                   comes from the outline, the dashes and the smaller radius. */
                <circle
                  key={`pt-${i}`}
                  cx={point.x} cy={point.y}
                  r={point.is_best ? 6 : 3.5}
                  {...(point.is_best ? {
                    className: 'chart__pr',
                    style: { '--at': (point.x / chart.width).toFixed(3) } as CSSProperties,
                    stroke: 'var(--done)',
                    strokeWidth: 1.5,
                  } : {})}
                  {...(point.is_deload ? { stroke: 'var(--unlit)', strokeWidth: 1.5 } : {})}
                  fill={point.is_deload
                    ? 'none'
                    : (point.is_best ? 'var(--record)' : 'var(--done)')}
                />
              ))}

              {chart.series.length > 1 && (
                <text
                  x={entry.label_x} y={entry.label_y} fill="var(--done)"
                  textAnchor={entry.label_anchor} fontSize="10" fontWeight="700"
                >
                  P{entry.position}
                </text>
              )}
            </g>
          ))}
        </g>

        {/* Hit targets, OUTSIDE .chart__ink: the golden-master test compares
            the ink group against the Jinja original, and these are
            interaction, not drawing. Radius 14 in viewBox units -- the dots
            themselves are 3.5, far below any usable touch target. */}
        <g aria-hidden="true" className="chart__hits">
          {picked !== null && (() => {
            const point = chart.series
              .find((entry) => entry.position === picked.position)
              ?.points[picked.index]
            return point === undefined ? null : (
              <circle className="chart__picked" cx={point.x} cy={point.y} r="8"
                fill="none" stroke="var(--ink)" strokeWidth="1.5" />
            )
          })()}
          {chart.series.map((entry) => entry.points.map((point, i) => (
            <circle
              key={`hit-${entry.position}-${i}`}
              cx={point.x} cy={point.y} r="14" fill="transparent"
              onClick={() => setPicked(
                picked?.position === entry.position && picked.index === i
                  ? null
                  : { position: entry.position, index: i })}
            />
          )))}
        </g>
      </svg>

      {/* What the tapped point is. A fixed line rather than a floating
          tooltip: nothing to position, nothing to clip at the chart edge,
          and the reserved height means tapping never shifts the page. Not a
          live region -- the readout is the pointer path's affordance, and the
          log below is the accessible one. */}
      <p className="chart__read">
        {(() => {
          const point: ChartPoint | undefined = picked === null ? undefined
            : chart.series.find((entry) => entry.position === picked.position)
              ?.points[picked.index]
          if (point === undefined) return <span className="chart__hint">Punkt antippen für Details</span>
          return (
            <>
              {shortDate(point.started_at)}
              {' · '}<b>{kg1(point.e1rm)} kg</b> e1RM
              {chart.series.length > 1 && ` · P${picked!.position}`}
              {point.is_best && <span className="chart__read-tag vtag vtag--record">Rekord</span>}
              {point.is_deload && <span className="chart__read-tag vtag vtag--neu">Deload</span>}
            </>
          )
        })()}
      </p>

      {/* Three marks, not two: with only the ends labelled there is nothing to
          judge the middle of the line against. The middle one is the middle
          DATE, computed with the geometry -- and deduped, so a history that is
          all one day renders one mark rather than the same date three times. */}
      <div className="chart__axis">
        {chart.dates.map((d) => <span className="label" key={d}>{d}</span>)}
      </div>

      {/* A key for a mark that is not on the chart is noise, so the legend only
          claims what was actually plotted. */}
      <div className="chart__legend">
        <span className="key">
          <span className="key__dot" style={{ background: 'var(--done)' }} />e1RM
        </span>
        {chart.has_record && (
          <span className="key">
            <span className="key__dot" style={{
              background: 'var(--record)',
              boxShadow: '0 0 0 1.5px var(--done)',
            }} />Rekord
          </span>
        )}
        {chart.has_deload && (
          <span className="key">
            <span className="key__dot" style={{
              background: 'transparent',
              boxShadow: 'inset 0 0 0 1.5px var(--unlit)',
            }} />Deload
          </span>
        )}
      </div>
    </div>
  )
}
