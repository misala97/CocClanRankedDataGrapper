import type { ExerciseAbout as About, ExerciseMeta } from '../types'
import { Icon } from './Icon'

/** "a, b und c" */
function joined(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(', ')} und ${items[items.length - 1]}` : items[0] ?? ''
}

interface Props {
  exercise: ExerciseMeta
  about: About
}

/** The exercise's drawing and what it trains. */
export function ExerciseArt({ exercise, about }: Props) {
  const also = exercise.secondary_muscle_groups ?? []
  return (
    <>
      {about.picture !== null && (
        <figure className="pic-full exabout__art">
          <img src={about.picture} alt={`Zeichnung: ${about.movement ?? exercise.name}`}
            width={640} height={640} />
        </figure>
      )}
      {exercise.muscle_group && (
        <p className="exabout__facts">
          Trainiert <b>{exercise.muscle_group}</b>{also.length > 0 ? `, dazu ${joined(also)}` : ''}.
        </p>
      )}
    </>
  )
}

/**
 * The other variants of the exercise's movement. Folded on a page with
 * history: there they are a way out, not the point, and a movement can have
 * thirteen of them. Open on the page of one never done (M6 screen 2): the
 * rack is taken, the Smith machine is free.
 */
export function ExerciseVariants({ about, open = false }: { about: About; open?: boolean }) {
  const count = about.variants.length
  if (about.movement === null || count === 0) return null
  const links = about.variants.map((variant) => (
    <a key={variant.id} className="exvar" href={`/gym/exercises/${variant.id}`}>
      {/* "Langhantel" alone names no exercise. */}
      <span className="sr-only">{`${about.movement} `}</span>
      {variant.label}
      <Icon name="forward" />
    </a>
  ))
  if (open) {
    return (
      <section className="exnew__alt" aria-labelledby="exalt-h">
        <h2 className="exnew__alt-h" id="exalt-h">{`${about.movement} auch mit`}</h2>
        {links}
      </section>
    )
  }
  return (
    <details className="exalt">
      <summary className="exalt__sum">
        {`${about.movement} auch mit `}
        <span className="exalt__n">{`${count} ${count === 1 ? 'Variante' : 'Varianten'}`}</span>
        <Icon name="down" />
      </summary>
      {links}
    </details>
  )
}

/** The exercise itself on a page with history (D9): its drawing, what it
 *  trains, and the other variants of its movement, folded. */
export function ExerciseAbout({ exercise, about }: Props) {
  return (
    <section className="exabout" aria-label="Die Übung">
      <ExerciseArt exercise={exercise} about={about} />
      <ExerciseVariants about={about} />
    </section>
  )
}
