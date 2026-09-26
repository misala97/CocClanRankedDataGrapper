import { useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { PictureTile } from '../session/components/Picture'
import { Sheet } from '../session/components/Sheet'
import { useSheets } from '../session/stores'
import type { FootOutcome } from '../session/usePartnerSync'
import { fetchPartnerList } from './api'
import { PARTNER_SHEET, PartnerTile, useRestRunning } from './PartnerLine'
import type { PartnerList, PartnerListRow, PartnerRef, ShownLink } from './types'
import {
  cutShort, footWords, inviteMeta, inviteNote, restSkipped, rowLoad, rowLoadSpoken, rowMeta,
  sheetMeta, sheetNote,
} from './words'

/** Whose list the sheet shows: the partner line or the "mit" tapped. */
export interface PartnerTarget {
  id: number
  username: string
  /** From the live screen: the line itself. An invite, answered or not, is
   *  shown from it alone; an open list is fetched again whenever it moves. */
  line?: ShownLink
}

/** What the live screen's sheet can do at its foot (B11). The debrief's and
 *  Verlauf's sheets only show, and get none. */
export interface PartnerFootActions {
  withdraw(id: number): Promise<FootOutcome>
  end(id: number): Promise<FootOutcome>
}

/** A second tap on a row that asked is its answer only this long after the
 *  first: sooner, it is the first one's bounce -- as the sheet's opening tap
 *  and an add have it (SHEET_OPEN_GUARD_MS, APPEND_GUARD_MS). And an end
 *  cannot be taken back: the two cannot be invited to this workout again. */
export const ASK_GUARD_MS = 600

/** The row at the sheet's foot that ends it for this viewer (M5): an invite
 *  taken back at one tap -- nothing is lost, they can be invited again --
 *  and training together ended or left at the second: the first asks, on
 *  the same row, as the add sheet's "Nochmal hinzufügen?" does. What the
 *  row does is decided by the line, fresh from the poll, never by the list:
 *  a list that would not load must not keep anyone in. */
function FootRow({ line, actions }: { line: ShownLink; actions: PartnerFootActions }) {
  const words = footWords(line)
  const close = useSheets((s) => s.close)
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const askedAt = useRef(0)
  // The sheet mounts its contents on open, so the asking belongs to this
  // visit to it -- and to the line as it is: a line that changed under it
  // starts it over.
  useEffect(() => {
    setArmed(false)
    setFailed(null)
  }, [line.id, line.state])
  // An answer that comes after the sheet was closed is not this visit's:
  // the line says what became of it, and the screen -- another sheet open
  // on it by then, perhaps -- is left alone.
  const here = useRef(true)
  useEffect(() => {
    here.current = true
    return () => { here.current = false }
  }, [])
  if (words === null) return null

  const act = async () => {
    setBusy(true)
    const outcome = await (line.state === 'invited'
      ? actions.withdraw(line.id) : actions.end(line.id))
    if (!here.current) return
    setBusy(false)
    // Done, or already so (404, 409): the line says what is so now.
    if (outcome.done) close()
    else setFailed(outcome.message)
  }
  const asking = words.ask !== null && armed
  return (
    <button type="button"
      className={['sheet-row', 'sheet-row--danger', 'psheet__act',
        asking || failed !== null ? 'is-armed' : '', busy ? 'is-busy' : '']
        .filter(Boolean).join(' ')}
      // Not `disabled`: that would drop the focus behind the sheet.
      aria-disabled={busy || undefined}
      onClick={() => {
        if (busy) return
        // The first tap asks. It stays asked through a request that did not
        // get through: the next tap sends it again.
        if (words.ask !== null && !armed) {
          askedAt.current = Date.now()
          setArmed(true)
          return
        }
        if (asking && Date.now() - askedAt.current < ASK_GUARD_MS) return
        void act()
      }}>
      <span className="sheet-row__lead"><Icon name="leave" /></span>
      <span className="sheet-row__main">
        <span className="sheet-row__name">{words.name}</span>
        {/* Over a hidden copy of the meta (data-room, gym.css): the ask, one
            line where the meta took two, must not pull the row down from
            under the thumb between its two taps. */}
        <span className="sheet-row__meta psheet__say" data-room={words.meta}>
          <span className="psheet__said" aria-live="polite">
            {failed ?? (asking ? words.ask : words.meta)}
          </span>
        </span>
      </span>
    </button>
  )
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

function ListBody({ target, dated, actions }: {
  target: PartnerTarget
  dated: boolean
  actions?: PartnerFootActions
}) {
  const { line } = target
  // The list's own fingerprint (partner_view._list_key): any row, any set,
  // not only the live one. And a rest begun or skipped -- not its seconds,
  // which move on every poll: the list counts those itself.
  const version = line === undefined
    ? '' : [line.state, line.list_key, line.rest_left === null].join('|')
  const { list, failed, receivedAt } = usePartnerList(target.id, version)
  const resting = useRestRunning(list?.rest_left ?? null, receivedAt)
  const foot = actions !== undefined && line !== undefined && footWords(line) !== null
    ? <FootRow line={line} actions={actions} /> : null
  const cut = list !== null && cutShort(list)
  // One tree whether the list is in or not: the foot keeps its place, so a
  // list arriving between its two taps does not start the asking over.
  return (
    <>
      <p className="psheet__meta">
        {list !== null
          ? sheetMeta(list, dated)
          : failed ? 'Die Liste ließ sich nicht laden.' : 'Lädt …'}
      </p>
      {list !== null && (
        <div className="psheet__list">
          {list.rows.map((row) => <Row key={row.id} row={row} resting={resting} cut={cut} />)}
        </div>
      )}
      {(list !== null || foot !== null) && (
        <div className="psheet__end">
          {list !== null && <p className="sheet__note">{sheetNote(list)}</p>}
          {foot}
        </div>
      )}
    </>
  )
}

function InviteBody({ line, actions }: { line: ShownLink; actions?: PartnerFootActions }) {
  return (
    <>
      <p className="psheet__meta">{inviteMeta(line)}</p>
      <p className="sheet__note">{inviteNote(line)}</p>
      {actions !== undefined && <FootRow line={line} actions={actions} />}
    </>
  )
}

/**
 * A training partner's workout, read-only (D14, M5): opened from a partner
 * line on the live screen, or from "mit <Name>" on a finished workout. The
 * exercises load when it opens; an exercise not started shows only its
 * count, never the weights planned for it (Michi).
 */
export function PartnerSheet({ target, dated = false, actions }: {
  target: PartnerTarget | null
  /** Opened from a finished workout: the list names its day. */
  dated?: boolean
  /** The live screen's: withdraw, end, leave (B11). */
  actions?: PartnerFootActions
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
        ? <InviteBody line={invite} actions={actions} />
        : <ListBody key={target.id} target={target} dated={dated} actions={actions} />)}
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
