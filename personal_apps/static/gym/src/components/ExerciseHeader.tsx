import type { ExerciseMeta } from '../types'
import { shortDate } from '../format'
import { Icon } from './Icon'

interface Props {
  exercise: ExerciseMeta
  lastOverall: { started_at: string; position: number } | null
  chipClass: string | null
  chipLabel: string | null
}

export function ExerciseHeader({ exercise, lastOverall, chipClass, chipLabel }: Props) {
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
        <h1 className="exdetail__name">{exercise.name}</h1>
        <span className="exdetail__sub">
          {exercise.muscle_group || 'Ohne Gruppe'}
          {/* lastOverall, not table[0]: `table` is the FILTERED view, so under
              ?position=5 this announced "Zuletzt ... Pos. 5" as though that
              were the last time you did the lift at all. Identity metadata is
              never scoped to a filter. */}
          {lastOverall !== null &&
            ` · Zuletzt ${shortDate(lastOverall.started_at)} · Pos. ${lastOverall.position}`}
          {exercise.is_unilateral && ' · einseitig'}
        </span>
      </span>
      {chipLabel !== null && <span className={`vtag vtag--${chipClass}`}>{chipLabel}</span>}
    </header>
  )
}
