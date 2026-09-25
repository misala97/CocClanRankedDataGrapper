import { useState } from 'react'
import type { RoutineChoice } from '../types'
import { postForm } from '../api'
import { uebungen } from '../catalogue/Band'
import { DialogSheet } from './DialogSheet'
import { Icon } from './Icon'

interface Props {
  exercise: { id: number; name: string }
  routines: RoutineChoice[]
  open: boolean
  onClose(): void
  /** The server's routines after an add: the page's, and so this sheet's. */
  onAdded(routines: RoutineChoice[]): void
}

/**
 * "Zur Routine" (M6 screen 2): the exercise goes at the end of the routine
 * tapped, with no plan of its own -- the routine's next start fills it in.
 * The sheet stays open: one exercise can go into two routines.
 */
export function RoutineSheet({ open, onClose, ...rest }: Props) {
  return (
    <DialogSheet id="sheet-routine" title="Zur Routine" open={open} onClose={onClose}>
      <Routines {...rest} />
    </DialogSheet>
  )
}

/** Mounted while open: what the last tap said goes when the sheet does. */
function Routines({ exercise, routines, onAdded }: Omit<Props, 'open' | 'onClose'>) {
  const [busy, setBusy] = useState<number | null>(null)
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null)

  const add = async (routine: RoutineChoice) => {
    if (busy !== null || routine.has) return
    setBusy(routine.id)
    setSaid(null)
    try {
      const answer = await postForm<{ routines: RoutineChoice[] }>(
        `/gym/templates/${routine.id}/exercises/add`, { exercise_id: exercise.id })
      onAdded(answer.routines)
      setSaid({ ok: true, text: `${exercise.name} ist jetzt in „${routine.name}“.` })
    } catch {
      setSaid({ ok: false, text: 'Nicht gespeichert. Nochmal antippen.' })
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <p className="rt__lead">{`${exercise.name} kommt ans Ende der Routine, die du antippst.`}</p>
      {routines.map((routine) => {
        // A button either way, "drin" too: the row just tapped stays the
        // element that has the focus when it turns. While an add is on its
        // way no row takes a tap, and the one sent is dimmed, as in the add
        // sheet: a slow add read as a tap that did nothing.
        const classes = ['sheet-row', 'rt__row']
        if (routine.has) classes.push('is-in')
        if (busy === routine.id) classes.push('is-busy')
        return (
          <button type="button" key={routine.id} className={classes.join(' ')}
            aria-disabled={routine.has || busy !== null || undefined}
            onClick={() => { void add(routine) }}>
            <span className="sheet-row__main">
              <span className="sheet-row__name">{routine.name}</span>
              <span className="sheet-row__meta">{uebungen(routine.count)}</span>
            </span>
            {routine.has
              ? <span className="rt__in"><Icon name="check" />drin</span>
              : <span className="rt__plus"><Icon name="plus" /></span>}
          </button>
        )
      })}
      <p className={said?.ok === false ? 'rt__said is-failed' : 'rt__said'} role="status">
        {said !== null && (
          <>
            {said.ok && <Icon name="check" />}
            {said.text}
          </>
        )}
      </p>
    </>
  )
}
