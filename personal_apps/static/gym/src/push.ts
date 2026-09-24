import { csrfToken } from './csrf'
import { usePush } from './session/stores'

/** What became of a tap on "Benachrichtigung aktivieren". */
export type PushOutcome = 'on' | 'dismissed' | 'denied' | 'failed' | 'unavailable'

/** The sentence each outcome that is not "on" shows beside the button. A
 *  dismissed prompt is a choice, not a failure, and says nothing. */
const WHY_NOT: Record<Exclude<PushOutcome, 'on'>, string | null> = {
  dismissed: null,
  denied: 'Benachrichtigungen sind blockiert. Erlaube sie in den Einstellungen und tippe noch einmal.',
  failed: 'Benachrichtigung ließ sich nicht aktivieren. Bitte noch einmal versuchen.',
  unavailable: 'Benachrichtigungen sind hier nicht eingerichtet.',
}

/** Rest notifications on for this device: the permission, a subscription at
 *  the push service, and the server told about it -- "on" only once the
 *  server said yes. The key comes from the page payload (null whenever VAPID
 *  is unset in .env).
 *
 *  One copy for every page that offers it. Start and the live workout each
 *  had their own, and neither read the server's answer nor caught a
 *  rejection, so a subscribe that failed looked like one that worked and
 *  took the button away (G-148). */
export async function subscribePush(vapidPublicKey: string | null): Promise<PushOutcome> {
  if (vapidPublicKey === null) return 'unavailable'
  try {
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/gym' })
    const permission = await Notification.requestPermission()
    if (permission === 'denied') return 'denied'
    if (permission !== 'granted') return 'dismissed'
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: urlBase64ToBytes(vapidPublicKey),
    })
    const response = await fetch('/gym/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
      body: JSON.stringify(subscription.toJSON()),
    })
    return response.ok ? 'on' : 'failed'
  } catch {
    return 'failed'
  }
}

/** subscribePush, with its answer in the shared push store: the device on,
 *  or the reason it is not, which each page shows beside its button. */
export async function enablePush(vapidPublicKey: string | null): Promise<void> {
  const outcome = await subscribePush(vapidPublicKey)
  const push = usePush.getState()
  if (outcome === 'on') push.setSubscribed(true)
  push.setError(outcome === 'on' ? null : WHY_NOT[outcome])
}

/** The VAPID key is base64url; PushManager wants raw bytes.
 *
 *  Returns ArrayBuffer rather than Uint8Array: applicationServerKey is typed
 *  BufferSource, and a Uint8Array's backing buffer is ArrayBufferLike, which
 *  admits SharedArrayBuffer and so does not satisfy it. */
function urlBase64ToBytes(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalised = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalised)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  return bytes.buffer
}

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
