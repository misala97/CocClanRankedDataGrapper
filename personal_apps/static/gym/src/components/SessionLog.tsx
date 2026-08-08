import type { E1rmPR, SessionRow, WeightPR } from '../types'
import { kg1, shortDate, volume } from '../format'

interface Props {
  table: SessionRow[]
  selectedPosition: number | null
  isUnilateral: boolean
  prWeight: WeightPR | null
  prE1rm: E1rmPR | null
}

export function SessionLog({
  table, selectedPosition, isUnilateral, prWeight, prE1rm,
}: Props) {
  return (
    <section className="sec sec--log" aria-labelledby="sec-log">
      {/* Same scoping as the chart above: this list is filtered too, and a
          bare "Einheiten" over 10 of 13 rows is a quiet miscount. */}
      <div className="sec__head">
        <h2 className="label" id="sec-log">Einheiten</h2>
        <span className="sec__sp" />
        <span className="label">
          {selectedPosition !== null ? `Pos. ${selectedPosition}` : 'Alle Positionen'}
        </span>
      </div>

      {isUnilateral && (
        <p className="exdetail__note">
          Einseitig: Gewicht &amp; Wdh. sind je Seite geloggt, Volumen zählt beide Seiten (×2).
        </p>
      )}

      {table.map((row) => {
        /* Matched on session_id, not started_at. Two sessions on one day both
           matched the date and both went gold; and because .row.is-record
           tinted .vol, the gold landed on VOLUME -- so a 1.656 kg row was gold
           while a 1.830 kg row below it was larger and plain. The record is an
           e1RM or a weight, never a volume. */
        const isE1rmPr = prE1rm !== null
          && row.session_id === prE1rm.session_id
          && row.position === prE1rm.position
        const isWeightPr = prWeight !== null
          && row.session_id === prWeight.session_id
          && row.position === prWeight.position
        const isRecord = isE1rmPr || isWeightPr

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
                {row.is_deload && <span className="vtag vtag--neu">Deload</span>}
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
              <span className="e1rm">{`e1RM ${kg1(row.e1rm)}`}</span>
            </span>
          </a>
        )
      })}

      <p className="exdetail__note">
        Deload-Einheiten bleiben in der Liste — sie sind das Protokoll. Sie halten
        keine Rekorde und zählen nicht gegen die Stagnation.
      </p>
    </section>
  )
}
