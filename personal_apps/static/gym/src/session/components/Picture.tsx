import { Icon } from '../../components/Icon'

/* The exercise drawings (round 4). Dark ink on a light plate the files are
   snapped to (gym_exercise_art/make_art.py), so plate and picture read as one
   surface; dark mode keeps the plate lit and dims both a little (gym.css
   --art-plate, --art-dim). The files are 640px squares: width and height hold
   the box before one arrives. */

/** The movement a drawing shows: one drawing per movement for now, so the
 *  list entry's equipment in brackets is not what is drawn -- Bankdrücken's
 *  shows the dumbbells, whichever entry it stands in for. */
export function movementOf(name: string): string {
  return name.replace(/\s*\([^)]*\)\s*$/, '')
}

export function Drawing({ src, alt = '', lazy = false }: { src: string; alt?: string; lazy?: boolean }) {
  return (
    <img src={src} alt={alt} width={640} height={640} decoding="async"
      {...(lazy ? { loading: 'lazy' as const } : {})} />
  )
}

/** A small tile: the drawing, or the dumbbell while the exercise has none
 *  yet. Decorative -- the exercise's name sits right beside it. */
export function PictureTile({ src, size }: { src: string | null; size: 'live' | 'queue' }) {
  if (src === null) {
    return (
      <span className={`pic pic--${size} pic--none`} aria-hidden="true">
        <Icon name="dumbbell" />
      </span>
    )
  }
  return (
    <span className={`pic pic--${size}`} aria-hidden="true">
      <Drawing src={src} lazy={size === 'queue'} />
    </span>
  )
}
