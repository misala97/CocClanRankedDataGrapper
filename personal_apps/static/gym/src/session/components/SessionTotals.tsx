import { useEffect, useState } from 'react'

interface Props {
  volume: number
  setsDone: number
  startedAt: string
}

function elapsed(startedAt: string, now: number): string {
  // Same format as the header's clock, and for the same reason: GymClock
  // always rendered hh:mm:ss.
  const total = Math.max(0, Math.floor((now - new Date(`${startedAt}Z`).getTime()) / 1000))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
}

/**
 * What the session has become. It is the reason the tick strip exists: the
 * number moves every time a set lands.
 *
 * The heading is for structure, not for the eye -- sighted readers take the
 * big number and its unit as the label. Without it the whole lower half of the
 * screen hung off no heading at all, so heading navigation went straight from
 * the live exercise to nothing.
 */
export function SessionTotals({ volume, setsDone, startedAt }: Props) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <>
      <h2 className="sr-only">Diese Einheit</h2>
      <div className="grew">
        <span className="grew__num">{Math.round(volume).toLocaleString('de-DE')}</span>
        <span className="grew__unit">kg bewegt</span>
        <span className="grew__sp" />
        <span className="grew__side">
          <b>{setsDone}</b>{` ${setsDone === 1 ? 'Satz' : 'Sätze'} · `}
          <b id="session-duration">{elapsed(startedAt, now)}</b>
        </span>
      </div>
    </>
  )
}
