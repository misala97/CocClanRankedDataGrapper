import type { LibraryEntry } from './types'
import type { Cluster, Section } from '../session/picker'
import { Band, bandCount, slug } from './Band'
import { useCatalogueUi } from './store'
import { Icon } from '../components/Icon'
import { PictureTile } from '../session/components/Picture'

const Chevron = () => <span className="nie-chev"><Icon name="forward" /></span>

/** One movement: its drawing once, its name, and each variant a way into
 *  that exercise's page -- a whole row to aim at (D13-A, "variants as
 *  rows"). A movement with one variant is one link. */
function Movement({ movement, rows }: Cluster<LibraryEntry>) {
  const picture = rows.find((row) => row.picture !== null)?.picture ?? null
  if (rows.length === 1) {
    const row = rows[0]!
    return (
      <a className="nie-move" href={`/gym/exercises/${row.id}`}>
        <PictureTile src={picture} size="list" />
        <span className="nie-move__body">
          <span className="nie-move__name">{movement}</span>{' '}
          <span className="nie-move__meta">{row.label}</span>
        </span>
        <Chevron />
      </a>
    )
  }
  return (
    <div className="nie-move">
      <PictureTile src={picture} size="list" />
      <div className="nie-move__body">
        <span className="nie-move__name">{movement}</span>
        <ul className="nie-vars">
          {rows.map((row) => (
            <li key={row.id}>
              {/* The movement for a link list read out of context:
                  "Kurzhantel" alone names no exercise. */}
              <a className="nie-var" href={`/gym/exercises/${row.id}`}>
                <span className="sr-only">{`${movement} `}</span>{row.label}
                <Chevron />
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/**
 * "Noch nie gemacht" (M6, D13-A): the rest of the list, so an exercise is
 * found before a workout and not only in a workout's add sheet (G-004).
 * Banded by the movement's group, as the add sheet bands it -- a movement
 * never splits -- and folded by default whatever its size: it is most of
 * the list. A search opens every band with a hit.
 */
export function NeverDone({ shown, sizes, searching, count, hasOwn }: {
  /** The bands with what they show: the hits', while searching. */
  shown: Section<LibraryEntry>[]
  /** Each band's size, for "3 von 12". */
  sizes: Map<string, number>
  searching: boolean
  /** The part's head: its hits, or its size. */
  count: number
  /** The lifter has exercises of their own: this is the rest, not all. */
  hasOwn: boolean
}) {
  const open = useCatalogueUi((s) => s.nieOpen)
  const toggle = useCatalogueUi((s) => s.toggleNie)
  return (
    <section className="ueb-part ueb-part--nie" aria-labelledby="nie-h">
      <h2 className="ueb-part__h" id="nie-h">
        Noch nie gemacht{' '}<span className="ueb-part__n">{count}</span>
      </h2>
      {!searching && (
        <p className="ueb-part__lead">
          {hasOwn ? 'Der Rest der Liste' : 'Die ganze Liste'}
          , nach Muskel und A–Z. Tipp eine Übung an, um sie anzusehen.
        </p>
      )}
      <div className="uebungen-nie">
        {shown.map(({ group, movements }) => {
          const expanded = searching || open.includes(group)
          const hits = movements.reduce((n, m) => n + m.rows.length, 0)
          return (
            // The id is the jump target of "Noch nichts für <group>".
            <section className="group-sec" key={group} id={`nie-${slug(group)}`}
              aria-labelledby={`n-${slug(group)}`}>
              <Band id={`n-${slug(group)}`} name={group} expanded={expanded}
                count={bandCount(hits, sizes.get(group) ?? hits, searching)}
                onToggle={() => toggle(group)} />
              {expanded && movements.map((cluster) => (
                <Movement key={cluster.movement} {...cluster} />
              ))}
            </section>
          )
        })}
      </div>
    </section>
  )
}
