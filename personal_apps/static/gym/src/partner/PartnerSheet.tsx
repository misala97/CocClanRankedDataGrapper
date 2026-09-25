import { useEffect, useState } from 'react'
import { Icon } from '../components/Icon'
import { PictureTile } from '../session/components/Picture'
import { Sheet } from '../session/components/Sheet'
import { fetchPartnerList } from './api'
import { PARTNER_SHEET, PartnerTile, useRestRunning } from './PartnerLine'
import type { PartnerLink, PartnerList, PartnerListRow, PartnerRef } from './types'
import {
  cutShort, inviteMeta, inviteNote, restSkipped, rowLoad, rowLoadSpoken, rowMeta, sheetMeta,
  sheetNote,
} from './words'

/** Whose list the sheet shows: the partner line or the "mit" tapped. */
export interface PartnerTarget {
  id: number
  username: string
  /** From the live screen: the line itself. An invite, answered or not, is
   *  shown from it alone; an open list is fetched again whenever it moves. */
  line?: PartnerLink
}

/** The list, fetched when the sheet opens and again whenever `version`
 *  changes -- the one shown stays until the next one has arrived. */
function usePartnerList(id: number, version: string) {
  const [state, setState] = useState<{
    id: number; list: PartnerList | null; failed: boolean; receivedAt: number
  }>({ id, list: null, failed: false, receivedAt: 0 })
  useEffect(() => {
    let current = true
    fetchPartnerList(id).then(
      (list) => { if (current) setState({ id, list, failed: false, receivedAt: Date.now() }) },
      () => {
        if (current) setState((s) => (s.id === id ? { ...s, failed: s.list === null } : s))
      })
    return () => { current = false }
  }, [id, version])
  return state.id === id ? state : { id, list: null, failed: false, receivedAt: 0 }
}

function Row({ row, resting, cut }: { row: PartnerListRow; resting: boolean; cut: boolean }) {
  const meta = rowMeta(row, resting)
  const cls = row.state === 'now' ? 'cur' : row.state
  return (
    <div className={`row psheet__row is-${cls}`}
      {...(row.state === 'now' ? { 'aria-current': 'step' as const } : {})}>
      <span className="row__lead queue__lead">
        {row.state === 'done' || restSkipped(row)
          ? <span className="queue__mark"><Icon name="check" /></span>
          : <PictureTile src={row.picture} size="queue" />}
      </span>
      <span className="row__main">
        <span className="row__name">{row.name}</span>
        {meta !== '' && <span className="row__meta">{meta}</span>}
      </span>
      <span className="row__trail queue__load">
        <span aria-hidden="true">{rowLoad(row, cut)}</span>
        <span className="sr-only">{rowLoadSpoken(row, cut)}</span>
      </span>
    </div>
  )
}

function ListBody({ target, dated }: { target: PartnerTarget; dated: boolean }) {
  const { line } = target
  // The list's own fingerprint (partner_view._list_key): any row, any set,
  // not only the live one. And a rest begun or skipped -- not its seconds,
  // which move on every poll: the list counts those itself.
  const version = line === undefined
    ? '' : [line.state, line.list_key, line.rest_left === null].join('|')
  const { list, failed, receivedAt } = usePartnerList(target.id, version)
  const resting = useRestRunning(list?.rest_left ?? null, receivedAt)
  if (list === null) {
    return <p className="psheet__meta">{failed ? 'Die Liste ließ sich nicht laden.' : 'Lädt …'}</p>
  }
  const cut = cutShort(list)
  return (
    <>
      <p className="psheet__meta">{sheetMeta(list, dated)}</p>
      <div className="psheet__list">
        {list.rows.map((row) => <Row key={row.id} row={row} resting={resting} cut={cut} />)}
      </div>
      {/* Ending, leaving and withdrawing come with B11, under the note. */}
      <div className="psheet__end"><p className="sheet__note">{sheetNote(list)}</p></div>
    </>
  )
}

function InviteBody({ line }: { line: PartnerLink }) {
  return (
    <>
      <p className="psheet__meta">{inviteMeta(line)}</p>
      <p className="sheet__note">{inviteNote(line)}</p>
    </>
  )
}

/**
 * A training partner's workout, read-only (D14, M5): opened from a partner
 * line on the live screen, or from "mit <Name>" on a finished workout. The
 * exercises load when it opens; an exercise not started shows only its
 * count, never the weights planned for it (Michi).
 */
export function PartnerSheet({ target, dated = false }: {
  target: PartnerTarget | null
  /** Opened from a finished workout: the list names its day. */
  dated?: boolean
}) {
  // An invite has no list yet -- nor ever, once it was declined: its sheet
  // says so from the line, and asks the server nothing.
  const line = target?.line
  const invite = line !== undefined && (line.state === 'invited' || line.state === 'declined')
    ? line : null
  return (
    <Sheet id={PARTNER_SHEET} title={target?.username ?? ''}
      lead={target !== null ? <PartnerTile username={target.username} /> : undefined}>
      {target !== null && (invite !== null
        ? <InviteBody line={invite} />
        : <ListBody key={target.id} target={target} dated={dated} />)}
    </Sheet>
  )
}

/** "mit <Name>" on a finished workout: the partner it was done with, whose
 *  list opens from here, frozen at their own finish (D14 screen 2). */
export function MitPartner({ partner, onOpen }: {
  partner: PartnerRef
  onOpen(partner: PartnerRef): void
}) {
  const n = partner.username
  return (
    <button type="button" className="mit" aria-haspopup="dialog" aria-controls={PARTNER_SHEET}
      aria-label={`Zusammen mit ${n}. Liste von ${n} ansehen`} onClick={() => onOpen(partner)}>
      <PartnerTile username={n} />
      <span className="mit__txt">mit <b>{n}</b></span>
      <Icon name="forward" />
    </button>
  )
}
