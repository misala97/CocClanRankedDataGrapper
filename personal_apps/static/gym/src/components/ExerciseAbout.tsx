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

/**
 * The exercise itself (D9 / M6 screen 2): its drawing, what it trains, and
 * the other variants of its movement. The variants are folded: on a page
 * with history they are a way out, not the point, and a movement can have
 * thirteen of them.
 */
export function ExerciseAbout({ exercise, about }: Props) {
  const also = exercise.secondary_muscle_groups ?? []
  const count = about.variants.length
  return (
    <section className="exabout" aria-label="Die Übung">
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
      {about.movement !== null && count > 0 && (
        <details className="exalt">
          <summary className="exalt__sum">
            {`${about.movement} auch mit `}
            <span className="exalt__n">{`${count} ${count === 1 ? 'Variante' : 'Varianten'}`}</span>
            <Icon name="down" />
          </summary>
          {about.variants.map((variant) => (
            <a key={variant.id} className="exvar" href={`/gym/exercises/${variant.id}`}>
              <span className="sr-only">{`${about.movement} `}</span>
              {variant.label}
              <Icon name="forward" />
            </a>
          ))}
        </details>
      )}
    </section>
  )
}
