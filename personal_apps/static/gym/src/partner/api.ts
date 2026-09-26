import { getJson, postForm } from '../api'
import type { PartnerList } from './types'

/** The partner's list, for the sheet behind a line or a "mit" -- loaded
 *  when that sheet opens (D14), never with the page. */
export function fetchPartnerList(sharedId: number): Promise<PartnerList> {
  return getJson<PartnerList>(`/gym/shared/${sharedId}/list.json`)
}

/** The leader's OK on a declined invite: the row goes with the line. */
export function dismissPartner(sharedId: number): Promise<{ ok: boolean }> {
  return postForm<{ ok: boolean }>(`/gym/shared/${sharedId}/dismiss`)
}

/** "Einladung zurückziehen": an invite nobody joined, taken back. 409 once
 *  they joined; the row goes, so they can be invited again (B11). */
export function withdrawInvite(sharedId: number): Promise<{ ok: boolean }> {
  return postForm<{ ok: boolean }>(`/gym/shared/${sharedId}/withdraw`)
}

/** "Gemeinsames Training beenden" or "Nicht mehr mitmachen": one route for
 *  either side of a joined link. 409 once it ended or a workout finished;
 *  404 once it is gone (B11). */
export function endPartner(sharedId: number): Promise<{ ok: boolean }> {
  return postForm<{ ok: boolean }>(`/gym/shared/${sharedId}/end`)
}
