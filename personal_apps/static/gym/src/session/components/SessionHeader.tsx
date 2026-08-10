import { useEffect, useState } from 'react'
import type { SessionMeta } from '../types'
import { useSheets } from '../stores'
import { Icon } from '../../components/Icon'

interface Props {
  session: SessionMeta
  /** Whether the deload percentage was actually applied to the weights. The
   *  session's is_deload flag is not the honest test: a session flagged after
   *  a set was already logged keeps its full working weights, and showing a
   *  percentage then describes nothing on screen. */
  deloadApplied: boolean
  deloadDefaultPct: number
}

/**
 * Elapsed workout time, as mm:ss or h:mm:ss.
 *
 * started_at is stored naive-UTC, so the 'Z' is appended rather than assumed.
 * This is a DIFFERENCE between two instants, which is the same number in any
 * timezone -- the original's GymClock made the same point in reverse, warning
 * that localising the start would shift the clock by the offset.
 */
function useElapsed(startedAt: string): string {
  const start = new Date(`${startedAt}Z`).getTime()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  // Always hh:mm:ss, zero-padded, exactly as GymClock rendered it. Dropping
  // the hours under an hour changes the header's width mid-workout and is not
  // what this clock did.
  const total = Math.max(0, Math.floor((now - start) / 1000))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
}

export function SessionHeader({ session, deloadApplied, deloadDefaultPct }: Props) {
  const openSheet = useSheets((s) => s.open)
  const elapsed = useElapsed(session.started_at)

  return (
    <header className="session-top">
      <a href="/gym" className="session-top__back" aria-label="Zurück zum Start">
        <Icon name="back" />
      </a>
      {/* The page's h1. It was a <span>, which left the whole document
          starting at h2 -- the live exercise's name -- so heading navigation
          returned one exercise and nothing about the workout. */}
      <h1 className="session-top__name">{session.name || 'Workout'}</h1>
      {session.is_deload && (
        <span className="session-top__deload">
          {deloadApplied
            ? `Deload ${session.deload_pct ?? deloadDefaultPct} %`
            : 'Deload'}
        </span>
      )}
      <span className="session-top__clock" id="session-clock">{elapsed}</span>
      <button type="button" className="session-top__more"
        aria-label="Workout-Optionen" onClick={() => openSheet('sheet-session')}>
        <Icon name="more" />
      </button>
    </header>
  )
}
