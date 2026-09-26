import { clockTime, kg, setsLine, weekdayDate } from '../format'
import type { PartnerList, PartnerListRow, PartnerSet, ShownLink } from './types'

/**
 * Every sentence the partner line and the partner's list say (D14, M5):
 * puls/m5_partner/build_m5.py words() and sheet(), build_m5s2.py. Kept apart
 * from the components so the copy is read in one place.
 *
 * Five states the mock left open, said here: a partner whose every set is
 * done but who has not finished ("alle Sätze geschafft"); the rest after the
 * last set ("Pause nach Satz 3 von 3" -- a rest is said by the sets DONE, so
 * it cannot read "nach Satz 2" there); a live exercise without sets
 * ("Satz 1"); nothing live, everything skipped ("ist dabei"); an invite's
 * sheet still open when the no arrives ("Abgelehnt um 11:30").
 */

/** "21 Sätze" and "1 Satz": a count with its noun. */
function sets(n: number): string {
  return `${n} ${n === 1 ? 'Satz' : 'Sätze'}`
}

/** "5 von 21 Sätzen": done of held, as the tick strip counts them. */
export function doneOf(done: number, total: number): string {
  return `${done} von ${total} ${total === 1 ? 'Satz' : 'Sätzen'}`
}

/** The finished line's count: "alle 21 Sätze", or "19 von 21 Sätzen". */
function finishedCount(link: ShownLink): string {
  if (link.sets_done === link.sets_total) {
    return link.sets_total === 1 ? sets(1) : `alle ${sets(link.sets_total)}`
  }
  return doneOf(link.sets_done, link.sets_total)
}

/** Where a joined partner is, without the name: "Satz 2 von 3",
 *  "Pause nach Satz 2 von 3", "Pause, dann Satz 1 von 3". */
function where(link: ShownLink, resting: boolean): string {
  const k = link.sets_in_exercise
  if (resting) {
    if (k === 0) return 'Pause'
    return link.done_in_exercise > 0
      ? `Pause nach Satz ${link.done_in_exercise} von ${k}`
      : `Pause, dann Satz ${link.set_no ?? 1} von ${k}`
  }
  if (link.set_no !== null) return `Satz ${link.set_no} von ${k}`
  return k > 0 ? 'alle Sätze geschafft' : 'Satz 1'
}

export interface LineWords {
  /** After the bold name: "ist eingeladen", "· Satz 2 von 3". */
  state: string
  /** The second line. */
  second: string
  /** The chip beside the second line: their last set of THIS exercise. */
  chip: PartnerSet | null
  /** The whole line as a screen reader says it, before ". Liste ansehen". */
  spoken: string
}

/** The follower's sentence once the order is theirs again. */
const ORDER_YOURS = 'Ab jetzt bestimmst du die Reihenfolge.'

export function lineWords(link: ShownLink, resting: boolean): LineWords {
  const n = link.username
  switch (link.state) {
    case 'invited':
      return {
        state: 'ist eingeladen', second: `Noch nicht dabei · seit ${clockTime(link.since)}`,
        chip: null, spoken: `${n} ist eingeladen, noch nicht dabei`,
      }
    case 'declined':
      return {
        // Not "allein": a second partner may be in.
        state: 'hat abgelehnt', second: `Du trainierst ohne ${n} weiter.`,
        chip: null, spoken: `${n} hat abgelehnt`,
      }
    case 'finished': {
      const count = finishedCount(link)
      return {
        state: 'ist fertig',
        second: link.viewer_leads && link.finished_at !== null
          ? `${clockTime(link.finished_at)} · ${count}`
          : ORDER_YOURS,
        chip: null, spoken: `${n} ist fertig, ${count}`,
      }
    }
    // Left or ended, the partner still training (B11). "allein" only of the
    // one who followed: a leader may train on with another partner still in.
    case 'ended':
      return {
        state: link.viewer_leads ? 'trainiert allein weiter' : 'trainiert weiter',
        second: link.viewer_leads ? 'Ihr trainiert jeder für sich weiter.' : ORDER_YOURS,
        chip: null,
        spoken: link.viewer_leads
          ? `${n} trainiert allein weiter`
          : `${n} trainiert weiter, ab jetzt bestimmst du die Reihenfolge`,
      }
    // The link went with a workout thrown away: nobody trains on in it, so
    // not "trainiert weiter". And over for the two of them only: another
    // partner may still be in.
    case 'vanished':
      return {
        state: 'ist nicht mehr dabei',
        second: link.viewer_leads ? 'Euer gemeinsames Training ist vorbei.' : ORDER_YOURS,
        chip: null,
        spoken: link.viewer_leads
          ? `${n} ist nicht mehr dabei`
          : `${n} ist nicht mehr dabei, ab jetzt bestimmst du die Reihenfolge`,
      }
    case 'joined': {
      if (link.exercise === null) {
        return {
          state: 'ist dabei', second: 'Keine Übung offen',
          chip: null, spoken: `${n} ist dabei, keine Übung offen`,
        }
      }
      const at = where(link, resting)
      const chip = link.last_set
      return {
        state: `· ${at}`, second: link.exercise, chip,
        spoken: `${n}: ${at}, ${link.exercise}`
          + (chip !== null ? `, zuletzt ${kg(chip.weight)} kg mal ${chip.reps}` : ''),
      }
    }
  }
}

/** The sheet's line under the name. `dated`: opened from a finished
 *  workout (the debrief, Verlauf), which names the day. */
export function sheetMeta(list: PartnerList, dated: boolean): string {
  const count = doneOf(list.sets_done, list.sets_total)
  if (list.finished_at !== null) {
    return dated
      ? `${weekdayDate(list.started_at)} · fertig um ${clockTime(list.finished_at)} · ${count}`
      : `Fertig um ${clockTime(list.finished_at)} · ${count}`
  }
  return list.link_live
    ? `Zusammen seit ${clockTime(list.since)} · ${count}`
    : `Trainiert noch · ${count}`
}

/** The note at the sheet's foot, above the row that ends it (footWords). */
export function sheetNote(list: PartnerList): string {
  const n = list.username
  if (list.finished_at !== null) return `So hat ${n} das Workout beendet. Nur zum Ansehen.`
  if (!list.link_live) return `Nur zum Ansehen: eintragen kann nur ${n}.`
  return list.viewer_leads
    ? `Nur zum Ansehen: eintragen kann nur ${n}. ${n} folgt deiner Reihenfolge.`
    : `Nur zum Ansehen: eintragen kann nur ${n}. Die Reihenfolge gibt ${n} vor, `
      + 'solange ihr zusammen trainiert.'
}

/** An invite's sheet, from its line alone: still waiting, or answered no. */
export function inviteMeta(link: ShownLink): string {
  return link.state === 'declined'
    ? `Abgelehnt um ${clockTime(link.since)}`
    : `Eingeladen um ${clockTime(link.since)} · noch keine Antwort`
}

export function inviteNote(link: ShownLink): string {
  // Not "allein" here either: a second partner may be in.
  return link.state === 'declined'
    ? `${link.username} trainiert nicht mit.`
    : `Sobald ${link.username} dabei ist, stehen hier die Übungen und Sätze, `
      + 'in deiner Reihenfolge.'
}

/** The row at the sheet's foot that ends it for this viewer (M5, B11): an
 *  invite taken back in one tap; training together ended by the one who
 *  leads, or left by the one who follows, each after asking once more. */
export interface FootWords {
  name: string
  meta: string
  /** What the row asks after the first tap; null: the first tap acts. */
  ask: string | null
}

export function footWords(link: ShownLink): FootWords | null {
  const n = link.username
  if (link.state === 'invited') {
    return { name: 'Einladung zurückziehen', meta: `${n} kann dann nicht mehr beitreten.`, ask: null }
  }
  if (link.state !== 'joined') return null
  return link.viewer_leads
    ? {
      name: 'Gemeinsames Training beenden', meta: `${n} trainiert allein weiter.`,
      ask: 'Wirklich beenden?',
    }
    : {
      name: 'Nicht mehr mitmachen',
      meta: 'Dein Workout läuft weiter, die Reihenfolge bestimmst dann du.',
      ask: 'Wirklich nicht mehr mitmachen?',
    }
}

/** The foot's row when its request did not get through: the next tap sends
 *  it again. */
export const FOOT_FAILED = 'Ging nicht durch — nochmal tippen.'

/** A row skipped after a set: what it got stays said, and that the rest was
 *  skipped -- as their own queue says it (G-065). */
export function restSkipped(row: PartnerListRow): boolean {
  return row.state === 'skipped' && row.done > 0
}

/** A row's second line: what was lifted, and on the row they are at, what
 *  they are doing now. An exercise not started says nothing here (Michi:
 *  never the planned weights). */
export function rowMeta(row: PartnerListRow, resting: boolean): string {
  const lifted = setsLine(row.sets)
  if (restSkipped(row)) return lifted === '' ? 'Rest übersprungen' : `${lifted} · Rest übersprungen`
  if (row.state !== 'now') return lifted
  const now = resting ? 'Pause' : `jetzt Satz ${row.set_no ?? 1}`
  return lifted === '' ? now : `${lifted} · ${now}`
}

/** Whether a list ended short of what it held. The finish took the open
 *  sets (D5), so its rows can only count what was ticked: "2/2" would call a
 *  row whole that was cut short, under a head saying "5 von 6". */
export function cutShort(list: PartnerList): boolean {
  return list.finished_at !== null && list.sets_done < list.sets_total
}

/** A row's count, as their own queue gives it: "2/4" -- a tick without reps
 *  counts, as there -- "1 Satz" for a row skipped after a set, "2" on a
 *  list cut short, or "–" for a row that was not done. */
export function rowLoad(row: PartnerListRow, cut: boolean): string {
  if (restSkipped(row)) return sets(row.done)
  if (row.state === 'skipped') return '–'
  return cut ? String(row.done) : `${row.done}/${row.done + row.open}`
}

/** The same count as a screen reader says it. */
export function rowLoadSpoken(row: PartnerListRow, cut: boolean): string {
  if (restSkipped(row)) return sets(row.done)
  if (row.state === 'skipped') return 'nicht gemacht'
  return cut ? sets(row.done) : doneOf(row.done, row.done + row.open)
}

/** The round tile's letter. */
export function initial(username: string): string {
  return (username.trim()[0] ?? '?').toUpperCase()
}
