// The per-session CSRF token, as board.html's <meta name="csrf-token">
// delivered it. Read lazily and memoised; the radar blueprint checks it on
// every write. The gym has the same three lines, on purpose: the two
// features share nothing.

let cached: string | null = null

export function csrfToken(): string {
  if (cached === null) {
    cached = document.querySelector('meta[name="csrf-token"]')
      ?.getAttribute('content') ?? ''
  }
  return cached
}

/** Test seam: jsdom documents have no shell meta. */
export function resetCsrfCache() {
  cached = null
}
