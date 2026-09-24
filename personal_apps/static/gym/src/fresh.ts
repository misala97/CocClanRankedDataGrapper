/**
 * A page restored from the back-forward cache is the page as it was left --
 * before the delete, the finish, the new record -- and every gym page carries
 * its data in its HTML. The server's answer now is a reload (G-141).
 *
 * The HTML is sent no-store, which keeps Chrome from restoring it at all;
 * Safari can restore it anyway, and this is what answers that. Every entry
 * installs it, before it renders anything.
 */
export function reloadWhenRestored(): () => void {
  const onShow = (event: PageTransitionEvent) => {
    if (event.persisted) window.location.reload()
  }
  window.addEventListener('pageshow', onShow)
  return () => window.removeEventListener('pageshow', onShow)
}
