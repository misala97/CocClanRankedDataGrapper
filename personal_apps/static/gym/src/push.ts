import { csrfToken } from './csrf'

/** Tell the server this device still holds the subscription it registered.
 *
 *  A push endpoint stays valid at the push service long after the browser
 *  that owns it has moved on -- a reinstall, cleared site data or a rotation
 *  gives the same device a NEW endpoint, and the old row keeps delivering
 *  because nothing ever 404s it. Since every notification fans out to every
 *  row a user owns, that is one extra buzz on the same phone, permanently.
 *  Production had four rows for one account, two of them per device.
 *
 *  So the server prunes on silence (features/gym/push.py), and this is the
 *  noise: an idempotent re-POST of the subscription the browser already has,
 *  sent on load by every page that checks whether push is on. The subscribe
 *  route is an upsert keyed on the endpoint, so this creates nothing new --
 *  it only refreshes last_seen_at.
 *
 *  Failures are swallowed on purpose. This is bookkeeping the user did not
 *  ask for, and a page must not surface an error for it. */
export function heartbeatSubscription(subscription: PushSubscription | null): void {
  if (subscription === null) return
  void fetch('/gym/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
    body: JSON.stringify(subscription.toJSON()),
  }).catch(() => { /* the next page load tries again */ })
}
