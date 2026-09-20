import { useEffect, useRef, useState } from 'react'
import { kg1, shortDate } from '../../format'
import { useCountUp } from '../../countup'
import { play } from '../confetti'
import { TAKEOVER_MS, type Celebration } from '../useRecordTakeover'

interface Props {
  celebration: Celebration
  onDismiss(): void
}

/** The count runs from the beaten number to the new one, so the slab shows the
 *  record being broken rather than stating it. Lands at 660ms of the 1000ms
 *  the takeover is up: the true number has to stand still for a beat, or the
 *  thing you actually wanted to see is the thing that got cut off. */
const COUNT_MS = 520
const COUNT_DELAY_MS = 140

/** Two bursts from the slab's bottom corners, aimed outward. One fountain from
 *  the middle throws gold confetti across a gold slab, and the number and the
 *  "vorher" line lose their contrast at exactly the moment they are the point.
 *  Angled out, the particles travel over the panel instead of over the type. */
const BURST_MS = 160
const BURST_AIM = 0.52
const BURST_SPREAD = 1.5
const BURST_COUNT = 23

/** Matches @keyframes rec-out (--dur-3). The hook unmounts the takeover at
 *  TAKEOVER_MS; the fade has to have finished by then, so it starts early
 *  rather than the hook waiting longer. Leaving is not a reverse of arriving:
 *  arriving is the event and gets the scale, leaving is just getting out of
 *  the way. */
const EXIT_MS = 180

const KINDS: Record<Celebration['record']['kind'], string> = {
  weight: 'Neuer Gewichts-Rekord',
  e1rm: 'Neuer e1RM-Rekord',
}

/**
 * One second of gold over the live panel when a set beats the exercise's best.
 *
 * It covers the panel on purpose. A record is the rarest thing this screen has
 * to say and the quiet note under the chips was reliably missed -- but it
 * covers it for one second, dismisses on a tap, and the chips underneath have
 * already gone gold by the time it lifts, so nothing is hidden that is not
 * still there afterwards.
 *
 * The confetti canvas is a sibling of the scrim rather than its child: the
 * scrim carries backdrop-filter, and a filtered ancestor makes `position:
 * fixed` resolve against that ancestor instead of the viewport, which would
 * trap every particle inside the panel.
 */
export function RecordTakeover({ celebration, onDismiss }: Props) {
  const { record, exerciseName, ordinal, position } = celebration
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const slabRef = useRef<HTMLDivElement | null>(null)

  // The target starts at `previous` and is moved to `value`, so the first
  // painted frame is the OLD number and the tween has somewhere to go.
  // useCountUp seeds itself from its target, so passing `value` directly
  // would show the answer immediately and animate nothing.
  const [target, setTarget] = useState(record.previous)
  const { shown } = useCountUp(target, COUNT_MS)
  useEffect(() => {
    const timer = setTimeout(() => setTarget(record.value), COUNT_DELAY_MS)
    return () => clearTimeout(timer)
  }, [record.value])

  const [leaving, setLeaving] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setLeaving(true), TAKEOVER_MS - EXIT_MS)
    return () => clearTimeout(timer)
  }, [])

  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    const canvas = canvasRef.current
    const slab = slabRef.current
    if (canvas === null || slab === null) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let stop: (() => void) | null = null
    const timer = setTimeout(() => {
      const box = slab.getBoundingClientRect()
      // The canvas is fixed to the viewport, so viewport coordinates map
      // straight through with no offset maths.
      const y = box.bottom - 8
      stop = play(canvas, [
        { x: box.left + 18, y, count: BURST_COUNT, spread: BURST_SPREAD, aim: -BURST_AIM },
        { x: box.right - 18, y, count: BURST_COUNT, spread: BURST_SPREAD, aim: BURST_AIM },
      ])
    }, BURST_MS)

    return () => {
      clearTimeout(timer)
      // Deliberately NOT stopped when the takeover lifts at 1000ms: the
      // particles outlive it, so the panel comes back mid-celebration instead
      // of snapping to a finished, quiet screen. This runs when the component
      // unmounts, which is later -- or immediately, on an early dismiss.
      if (stop !== null) stop()
    }
  }, [])

  return (
    <div className={leaving ? 'record-takeover is-out' : 'record-takeover'}
      role="status" onClick={onDismiss}>
      <div className="record-takeover__scrim" />
      <div className="record-takeover__slab" ref={slabRef}>
        <div className="record-takeover__kind">{KINDS[record.kind]}</div>
        <div className="record-takeover__name">{`${exerciseName} · Satz ${ordinal}`}</div>
        <div className="record-takeover__row">
          <span className="record-takeover__num">{kg1(shown)}</span>
          <span className="record-takeover__unit">kg</span>
        </div>
        <div className="record-takeover__prev">
          {`vorher ${kg1(record.previous)} kg · ${shortDate(record.previous_at).slice(0, 6)}`
            + ` · als ${position}. Übung`}
        </div>
      </div>
      <canvas className="record-takeover__fx" ref={canvasRef} aria-hidden="true" />
    </div>
  )
}
