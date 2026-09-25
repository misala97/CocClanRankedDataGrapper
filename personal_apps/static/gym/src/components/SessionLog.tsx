import type { SessionRow } from '../types'
import { kg1, shortDate, volume } from '../format'

interface Props {
  table: SessionRow[]
  selectedPosition: number | null
  isUnilateral: boolean
}

export function SessionLog({ table, selectedPosition, isUnilateral }: Props) {
  return (
    <section className="sec sec--log" aria-labelledby="sec-log">
      {/* Same scoping as the chart above: this list is filtered too, and a
          bare "Workouts" over 10 of 13 rows is a quiet miscount. */}
      <div className="sec__head">
        <h2 className="label" id="sec-log">Workouts</h2>
        <span className="sec__sp" />
        <span className="label">
          {selectedPosition !== null ? `Pos. ${selectedPosition}` : 'Alle Positionen'}
        </span>
      </div>

      {isUnilateral && (
        <p className="exdetail__note">
          Gewicht je Seite geloggt; das Volumen zählt beide Seiten (×2).
        </p>
      )}

      {table.map((row) => {
        /* The server's mark, per row: this workout's e1RM beat every one
           before it (D3). History -- a record later overtaken keeps its tag,
           as its badge does everywhere else. It used to be matched here
           against the one best set, by session. */
        const isRecord = row.is_record

        return (
          <a
            key={`${row.session_id}-${row.position}`}
            className={`row row--top${isRecord ? ' is-record' : ''}`}
            href={`/gym/session/${row.session_id}`}
          >
            <span className="row__main stack">
              <span className="dateline">
                <span className="dateline__d">{shortDate(row.started_at)}</span>
                {/* A word as well as the colour: the tint alone was the only
                    carrier, so a record was invisible in greyscale and absent
                    for a screen reader. */}
                {isRecord && <span className="vtag vtag--record">Rekord</span>}
                {row.is_deload && <span className="vtag vtag--deload">Deload</span>}
              </span>
              {/* One template literal, not interpolated JSX children: React
                  would emit a separate text node per expression, and the
                  browser rounds glyph advances per run -- which changes
                  antialiasing against the single text node Jinja produced.
                  Nothing moves either way, but this keeps the raster
                  identical. */}
              <span className="row__meta">{`Pos. ${row.position} · ${row.sets_display}`}</span>
            </span>
            <span className="row__trail row__trail--stack">
              <span className="vol">{volume(row.volume)}<small>kg</small></span>
              <span className="e1rm">{`1RM ${kg1(row.e1rm)}`}</span>
            </span>
          </a>
        )
      })}

      <p className="exdetail__note">
        Rekord heißt: das beste 1RM bis zu diesem Tag. Deload-Workouts bleiben
        in der Liste — sie sind das Protokoll — und zählen nicht gegen die
        Stagnation.
      </p>
    </section>
  )
}
