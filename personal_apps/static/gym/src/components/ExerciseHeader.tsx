import type { ExerciseMeta } from '../types'
import { Icon } from './Icon'

interface Props {
  exercise: ExerciseMeta
  chipClass: string | null
  chipLabel: string | null
}

export function ExerciseHeader({ exercise, chipClass, chipLabel }: Props) {
  return (
    <header className="session-top">
      <a href="/gym/uebungen" className="session-top__back"
        aria-label="Zurück zu den Übungen">
        <Icon name="back" />
      </a>
      <span className="session-top__name stack">
        {/* The page's h1. It had NO heading of any level -- the exercise name
            was a span, so the document outline was empty and heading
            navigation had nothing to land on. */}
        <h1 className="exdetail__name" style={{ viewTransitionName: 'ex' }}>{exercise.name}</h1>
        {/* When it was last done is the lead's "Letztes Mal" now, and the
            slot it ran in is no longer a word on screen (D9, D16).

            Assembled into one string rather than interpolated as JSX children:
            React emits a text node per expression and the browser rounds glyph
            advances per run, which changes antialiasing against the single
            text node Jinja produced. Nothing moves either way; this keeps the
            raster identical. */}
        <span className="exdetail__sub">
          {[
            exercise.muscle_group || 'Ohne Muskelgruppe',
            exercise.is_unilateral ? 'Gewicht je Seite' : null,
          ].filter(Boolean).join(' · ')}
        </span>
      </span>
      {chipLabel !== null && <span className={`vtag vtag--${chipClass}`}>{chipLabel}</span>}
    </header>
  )
}
