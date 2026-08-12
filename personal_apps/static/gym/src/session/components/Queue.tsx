import { useEffect, useRef, useState } from 'react'
import type { LiveExercise } from '../types'
import { useAnnouncer, useSheets, useWorkoutUi } from '../stores'
import { Icon } from '../../components/Icon'
import { kg1 } from '../../format'

interface Props {
  exercises: LiveExercise[]
  liveId: number | null
  onReorder: (order: number[]) => void
}

/** What the trailing column says, which differs by what the row is. */
function loadSummary(se: LiveExercise, isLive: boolean): string {
  const done = se.sets.filter((s) => s.completed).length
  const total = se.sets.length
  if (se.skipped) return 'Übersprungen'
  if (isLive) return `${done}/${total}`
  if (total > 0 && done === total) return `${done}/${total}`
  if (total > 0) {
    return `${total} × ${kg1(se.sets[0]!.weight)}`
  }
  return '—'
}

/* Ported from session_reorder.js: the threshold that separates a tap from a
 * drag, and the screen-edge band that auto-scrolls a long queue while
 * dragging. touch-action: none on the handle is what stops the browser
 * claiming the gesture as a scroll before the threshold is reached. */
const DRAG_THRESHOLD = 8
const SCROLL_EDGE = 80
const SCROLL_SPEED = 16

interface DragState {
  seId: number
  pointerId: number
  startY: number
  lastY: number
  baseY: number
  active: boolean
  ghost: HTMLElement | null
  rafId: number | null
  order: number[]
  /** Removes the window listeners this drag installed. See onPointerDown. */
  detach: (() => void) | null
}

/**
 * The whole workout in order, INCLUDING the exercise you are on.
 *
 * Filtering the live one out left a hole in the sequence -- the list ran
 * 1, 3, 4 with nothing saying where you were, so it stopped being a map of the
 * session and became a list of leftovers. The live row duplicating the panel's
 * name is the point: the panel above is the workspace, this is the position.
 *
 * Reorder mode lives here too. The visuals key off `.queue.is-reordering` --
 * a class THIS component writes from the store, not a body class some other
 * script has to remember to set: the Jinja-era body-class contract is how the
 * mode shipped dead once already.
 */
export function Queue({ exercises, liveId, onReorder }: Props) {
  const openSheet = useSheets((s) => s.open)
  const reordering = useWorkoutUi((s) => s.reorderUnlocked)
  const announce = useAnnouncer((s) => s.announce)

  // While a drag is in flight the list renders from this order, not from the
  // payload -- the payload only learns the result on drop. Null outside one.
  const [dragOrder, setDragOrder] = useState<number[] | null>(null)
  const [draggedId, setDraggedId] = useState<number | null>(null)

  const rowRefs = useRef(new Map<number, HTMLDivElement>())
  const handleRefs = useRef(new Map<number, HTMLButtonElement>())
  const drag = useRef<DragState | null>(null)
  const pendingFocus = useRef<number | null>(null)

  // Leaving the mode always discards a half-done drag.
  useEffect(() => {
    if (!reordering) {
      setDragOrder(null)
      setDraggedId(null)
      drag.current = null
    }
  }, [reordering])

  // After a committed drop the payload catches up (optimistically, then with
  // the server's answer); once it re-renders, the local override retires.
  useEffect(() => {
    if (dragOrder !== null && drag.current === null && draggedId === null) {
      setDragOrder(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exercises])

  // Moving a focused node can blur it, and a reorder that ejects a keyboard
  // user from the row they are moving is not one anyone can finish -- refocus
  // the moved row's handle after React commits the new order.
  useEffect(() => {
    if (pendingFocus.current !== null) {
      handleRefs.current.get(pendingFocus.current)?.focus()
      pendingFocus.current = null
    }
  })

  const ordered = dragOrder === null
    ? exercises
    : dragOrder.flatMap((id) => {
      const se = exercises.find((x) => x.id === id)
      return se ? [se] : []
    })

  function moveByKey(se: LiveExercise, key: 'ArrowUp' | 'ArrowDown') {
    const ids = ordered.map((x) => x.id)
    const i = ids.indexOf(se.id)
    const j = key === 'ArrowUp' ? i - 1 : i + 1
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j]!, ids[i]!]
    pendingFocus.current = se.id
    // The rows moving is a purely visual event; this is the only feedback a
    // screen reader gets.
    announce(`${se.name}, Position ${j + 1} von ${ids.length}.`)
    onReorder(ids)
  }

  function beginDrag(handle: HTMLButtonElement) {
    const d = drag.current
    if (d === null) return
    const row = rowRefs.current.get(d.seId)
    if (row === undefined) return
    d.active = true
    // Capture is still asked for -- it keeps hover and text selection off the
    // rows the ghost passes over -- but nothing depends on it surviving; the
    // window listeners in onPointerDown are what carry the gesture.
    try { handle.setPointerCapture(d.pointerId) } catch { /* not fatal */ }

    const rect = row.getBoundingClientRect()
    d.baseY = d.lastY

    // The ghost is a throwaway clone that follows the finger; the real row
    // stays in the list (dimmed) and moves through it as the ghost crosses
    // its neighbours' midlines.
    const ghost = row.cloneNode(true) as HTMLElement
    ghost.removeAttribute('id')
    ghost.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'))
    ghost.classList.add('drag-ghost')
    ghost.setAttribute('inert', '')
    Object.assign(ghost.style, {
      position: 'fixed',
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      top: `${rect.top}px`,
      margin: '0',
      pointerEvents: 'none',
    })
    document.body.appendChild(ghost)
    d.ghost = ghost

    setDraggedId(d.seId)
    setDragOrder([...d.order])
    if (d.rafId === null) d.rafId = requestAnimationFrame(autoScroll)
  }

  function moveDrag(clientY: number) {
    const d = drag.current
    if (d?.ghost == null) return
    d.ghost.style.transform = `translateY(${clientY - d.baseY}px)`

    const g = d.ghost.getBoundingClientRect()
    const centre = g.top + g.height / 2
    const i = d.order.indexOf(d.seId)

    const next = d.order[i + 1]
    if (next !== undefined) {
      const r = rowRefs.current.get(next)?.getBoundingClientRect()
      if (r && centre > r.top + r.height / 2) {
        ;[d.order[i], d.order[i + 1]] = [next, d.seId]
        setDragOrder([...d.order])
        return
      }
    }
    const prev = d.order[i - 1]
    if (prev !== undefined) {
      const r = rowRefs.current.get(prev)?.getBoundingClientRect()
      if (r && centre < r.top + r.height / 2) {
        ;[d.order[i - 1], d.order[i]] = [d.seId, prev]
        setDragOrder([...d.order])
      }
    }
  }

  function autoScroll() {
    const d = drag.current
    if (d === null || !d.active) {
      if (d !== null) d.rafId = null
      return
    }
    const vh = window.innerHeight
    let delta = 0
    if (d.lastY < SCROLL_EDGE) {
      delta = -Math.ceil(SCROLL_SPEED * (SCROLL_EDGE - d.lastY) / SCROLL_EDGE)
    } else if (d.lastY > vh - SCROLL_EDGE) {
      delta = Math.ceil(SCROLL_SPEED * (d.lastY - (vh - SCROLL_EDGE)) / SCROLL_EDGE)
    }
    if (delta !== 0) {
      window.scrollBy(0, delta)
      moveDrag(d.lastY)
    }
    d.rafId = requestAnimationFrame(autoScroll)
  }

  function endDrag(commit: boolean) {
    const d = drag.current
    if (d === null) return
    const wasActive = d.active
    d.detach?.()
    if (d.rafId !== null) cancelAnimationFrame(d.rafId)
    d.ghost?.remove()
    const handle = handleRefs.current.get(d.seId)
    if (handle) { try { handle.releasePointerCapture(d.pointerId) } catch { /* gone */ } }
    drag.current = null
    setDraggedId(null)
    if (wasActive && commit) {
      // dragOrder stays up until the payload re-renders with this order (the
      // effect above), so the list never flashes back to the old sequence.
      onReorder(d.order)
    } else {
      setDragOrder(null)
    }
  }

  /**
   * The rest of the gesture is watched on `window`, not on the handle.
   *
   * setPointerCapture is not enough here and cannot be: the first swap moves
   * the handle's DOM node, and a captured element that leaves the document --
   * even for a moment, even to be reinserted two rows down -- loses the
   * capture. From that point the events go to whatever happens to be under
   * the cursor, so the pointerup that COMMITS the drag was landing on the
   * finish button and `endDrag` never ran: nothing was saved, and the ghost
   * clone and the dimmed row stayed on screen until a reload. Touch never
   * showed it, because a touch pointer is implicitly captured by its target.
   */
  function onPointerDown(se: LiveExercise, e: React.PointerEvent<HTMLButtonElement>) {
    if (!reordering) return
    const handle = e.currentTarget
    const pointerId = e.pointerId

    const onMove = (ev: PointerEvent) => {
      const d = drag.current
      if (d === null || ev.pointerId !== pointerId) return
      d.lastY = ev.clientY
      if (!d.active) {
        if (Math.abs(ev.clientY - d.startY) < DRAG_THRESHOLD) return
        beginDrag(handle)
      }
      ev.preventDefault()
      moveDrag(ev.clientY)
    }
    const onUp = (ev: PointerEvent) => {
      if (ev.pointerId !== pointerId) return
      endDrag(true)
    }
    const onCancel = (ev: PointerEvent) => {
      if (ev.pointerId !== pointerId) return
      endDrag(false)
    }

    drag.current = {
      seId: se.id,
      pointerId,
      startY: e.clientY,
      lastY: e.clientY,
      baseY: 0,
      active: false,
      ghost: null,
      rafId: null,
      order: ordered.map((x) => x.id),
      detach: () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
        window.removeEventListener('pointercancel', onCancel)
      },
    }
    // passive: false -- onMove calls preventDefault to keep the page from
    // scrolling under an in-progress drag.
    window.addEventListener('pointermove', onMove, { passive: false })
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onCancel)
    e.preventDefault()
  }

  return (
    <div className={`queue${reordering ? ' is-reordering' : ''}`} id="queue">
      <h2 className="sr-only">Übungen</h2>

      {ordered.map((se) => {
        const done = se.sets.filter((s) => s.completed).length
        const total = se.sets.length
        const isLive = se.id === liveId
        const isDone = total > 0 && done === total

        const className = [
          'row queue__row',
          isLive ? 'is-now' : '',
          isDone ? 'is-done' : '',
          se.skipped ? 'is-skipped' : '',
          draggedId === se.id ? 'is-dragging' : '',
        ].filter(Boolean).join(' ')

        return (
          <div className={className} data-se-id={se.id} key={se.id}
            ref={(el) => {
              if (el) rowRefs.current.set(se.id, el)
              else rowRefs.current.delete(se.id)
            }}>
            {/* A real button, not an aria-hidden span. Dragging is one way to
                move a row; focusing this and pressing ArrowUp/ArrowDown is the
                other, and without that second one reordering was impossible by
                keyboard and invisible to a screen reader. Only in the tab
                order while the mode is on, because outside it this does
                nothing and four inert stops between rows is worse than none. */}
            <button type="button" className="drag-handle"
              ref={(el) => {
                if (el) handleRefs.current.set(se.id, el)
                else handleRefs.current.delete(se.id)
              }}
              tabIndex={reordering ? 0 : -1}
              aria-label={`${se.name} verschieben`}
              onPointerDown={(e) => onPointerDown(se, e)}
              onKeyDown={(e) => {
                if (!reordering) return
                if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
                e.preventDefault()
                moveByKey(se, e.key)
              }}>⠿</button>

            {/* Never colour alone: a tick for finished, a filled dot for the
                one you are on, the slot number for one still ahead. */}
            <span className="row__lead queue__lead">
              {isLive
                ? <span className="queue__now" aria-hidden="true" />
                : isDone
                  ? <span className="queue__mark"><Icon name="check" /></span>
                  : se.position}
            </span>

            <button type="button" className="row__main"
              {...(isLive ? { 'aria-current': 'step' as const } : {})}
              onClick={() => openSheet(`sheet-ex-${se.id}`)}>
              <span className="row__name">{se.name}</span>
            </button>

            <span className="row__trail queue__load">{loadSummary(se, isLive)}</span>
          </div>
        )
      })}

      {/* Adding an exercise lived only in the sheet in the top corner, which is
          the wrong end of the screen and the wrong place to look: the queue is
          where you are already reading what the workout contains.

          Not a .queue__row and carrying no data-se-id -- the drag and
          arrow-key paths key off those, and an action is not a position in
          the sequence. Hidden during a reorder for the same reason: every row
          in this list is then a thing being moved. */}
      {!reordering && (
        <div className="row queue__add">
          <span className="row__lead queue__lead" aria-hidden="true">
            <Icon name="plus" />
          </span>
          <button type="button" className="row__main"
            onClick={() => openSheet('sheet-add-exercise')}>
            <span className="row__name">Übung hinzufügen</span>
          </button>
        </div>
      )}
    </div>
  )
}
