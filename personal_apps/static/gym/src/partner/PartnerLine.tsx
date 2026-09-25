import { useEffect, useState } from 'react'
import { Icon } from '../components/Icon'
import { kg } from '../format'
import type { PartnerLink } from './types'
import { initial, lineWords } from './words'

/** The one sheet a partner's list opens in, on every page that has one. */
export const PARTNER_SHEET = 'sheet-partner'

/** The partner's round tile: their initial. Round, so it never reads as an
 *  exercise's picture. */
export function PartnerTile({ username }: { username: string }) {
  return <span className="partner__tile" aria-hidden="true">{initial(username)}</span>
}

/** Whether a rest `restLeft` seconds long at `receivedAt` still runs --
 *  re-rendering the moment it ends, so "Pause" turns into the next set on
 *  time without waiting for the next poll. */
export function useRestRunning(restLeft: number | null, receivedAt: number): boolean {
  const ends = restLeft === null ? null : receivedAt + restLeft * 1000
  const [, rerender] = useState(0)
  useEffect(() => {
    if (ends === null) return
    const wait = ends - Date.now()
    if (wait <= 0) return
    const timer = setTimeout(() => rerender((n) => n + 1), wait)
    return () => clearTimeout(timer)
  }, [ends])
  return ends !== null && Date.now() < ends
}

interface LineProps {
  link: PartnerLink
  receivedAt: number
  onOpen(link: PartnerLink): void
  onDismiss(id: number): void
}

/**
 * One training partner, one line under the header (D14, M5 variant A).
 *
 * Always 52 px, whatever it says: a poll that changes what it says must
 * never move "Satz geschafft" under a thumb. The whole line opens the
 * partner's list; a declined invite has no list, only its OK.
 */
function PartnerLine({ link, receivedAt, onOpen, onDismiss }: LineProps) {
  const resting = useRestRunning(link.state === 'joined' ? link.rest_left : null, receivedAt)
  const words = lineWords(link, resting)
  const main = (
    <span className="partner__main">
      <span className="partner__who">
        <b>{link.username}</b>{' '}<span className="partner__state">{words.state}</span>
      </span>
      <span className="partner__what">
        <span className="partner__ex">{words.second}</span>
        {words.chip !== null && (
          <span className="partner__set">
            <Icon name="check" />{`${kg(words.chip.weight)} × ${words.chip.reps}`}
          </span>
        )}
      </span>
    </span>
  )

  if (link.state === 'declined') {
    return (
      <div className="partner is-declined" role="status">
        <div className="partner__hit">
          <PartnerTile username={link.username} />
          {main}
          <button type="button" className="partner__ok" onClick={() => onDismiss(link.id)}>
            OK
          </button>
        </div>
      </div>
    )
  }
  return (
    <div className={`partner is-${link.state}`}>
      <button type="button" className="partner__hit" aria-haspopup="dialog"
        aria-controls={PARTNER_SHEET} aria-label={`${words.spoken}. Liste ansehen`}
        onClick={() => onOpen(link)}>
        <PartnerTile username={link.username} />
        {main}
        <span className="partner__chev"><Icon name="forward" /></span>
      </button>
    </div>
  )
}

/** Every partner line of the workout, in the order they were invited. */
export function PartnerLines({ links, receivedAt, onOpen, onDismiss }: {
  links: PartnerLink[]
  receivedAt: number
  onOpen(link: PartnerLink): void
  onDismiss(id: number): void
}) {
  if (links.length === 0) return null
  return (
    <div className="partners">
      {links.map((link) => (
        <PartnerLine key={link.id} link={link} receivedAt={receivedAt}
          onOpen={onOpen} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
