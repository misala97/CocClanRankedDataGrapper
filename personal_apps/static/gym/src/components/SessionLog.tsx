import { useRef, useState } from 'react'
import type { SessionRow } from '../types'
import { kg1, setsLine, volume, weekdayDate } from '../format'
import { Icon } from './Icon'

/** The newest this many rows show; the rest behind "Alle N Workouts zeigen". */
const SHOWN = 5

interface Props {
  table: SessionRow[]
  isUnilateral: boolean
}

/**
 * Every workout of the exercise, newest first (D9, M2): the day, the sets as
 * one line, the volume and the 1RM. The whole exercise -- the pills above
 * lens the Rekordtreppe only. Five rows, then all of them on request: the
 * log backs the page up, it is not its point.
 */
export function SessionLog({ table, isUnilateral }: Props) {
  const [all, setAll] = useState(false)
  const firstMore = useRef<HTMLAnchorElement>(null)
  // One row per slot: an exercise done at two positions in one workout is
  // two rows here and still one workout (D16).
  const workouts = new Set(table.map((row) => row.session_id)).size
  const rows = all ? table : table.slice(0, SHOWN)

  return (
    <section className="exsec" aria-labelledby="sec-log">
      <h2 className="exsec__h" id="sec-log">
        Workouts <span className="exsec__n">{workouts}</span>
      </h2>
      {isUnilateral && (
        <p className="exsec__in">Gewicht je Seite geloggt; das Volumen zählt beide Seiten (×2).</p>
      )}
      <div className="exlog">
        {rows.map((row, i) => (
          <a
            key={`${row.session_id}-${row.position}`}
            ref={i === SHOWN ? firstMore : undefined}
            className={`row row--top${row.is_record ? ' is-record' : ''}`}
            href={`/gym/session/${row.session_id}`}
          >
            <span className="row__main stack">
              <span className="dateline">
                <span className="dateline__d">{weekdayDate(row.started_at)}</span>
                {/* A word as well as the colour: the tint alone was invisible
                    in greyscale and absent for a screen reader. */}
                {row.is_record && <span className="vtag vtag--record">Rekord</span>}
                {row.is_deload && <span className="vtag vtag--deload">Deload</span>}
              </span>
              <span className="row__meta">{setsLine(row.sets)}</span>
            </span>
            <span className="row__trail row__trail--stack">
              <span className="vol">{volume(row.volume)}<small>kg</small></span>
              {/* 0 kg sets estimate nothing: "1RM 0,0" on every bodyweight
                  row was noise (G-038). */}
              {row.e1rm > 0 && <span className="e1rm">{`1RM ${kg1(row.e1rm)}`}</span>}
            </span>
          </a>
        ))}
      </div>
      {!all && table.length > SHOWN && (
        <button type="button" className="sec__more exlog__more"
          onClick={() => {
            setAll(true)
            // The button goes with the click: focus lands on the first row it
            // brought, not on the page's top.
            requestAnimationFrame(() => firstMore.current?.focus())
          }}>
          {`Alle ${workouts} Workouts zeigen`}
          <Icon name="down" />
        </button>
      )}
      <p className="exnote">
        Rekord: das beste geschätzte Maximum bis zu diesem Tag. Deload-Workouts stehen in der
        Liste und zählen nicht gegen die Stagnation.
      </p>
    </section>
  )
}
