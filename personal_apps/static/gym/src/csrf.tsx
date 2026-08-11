// The per-session CSRF token, as the shell's <meta name="csrf-token">
// delivered it. Read lazily and memoised: the meta is static for the life of
// the document, but module-eval order must not depend on <head> being parsed.

let cached: string | null = null

export function csrfToken(): string {
  if (cached === null) {
    cached = document.querySelector('meta[name="csrf-token"]')
      ?.getAttribute('content') ?? ''
  }
  return cached
}

/** The hidden field every native form carries -- the form-post twin of the
 *  X-CSRF-Token header src/api.ts sends on every fetch. */
export function CsrfField() {
  return <input type="hidden" name="csrf_token" value={csrfToken()} />
}

/** Test seam: jsdom documents have no shell meta. */
export function resetCsrfCache() {
  cached = null
}
