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
