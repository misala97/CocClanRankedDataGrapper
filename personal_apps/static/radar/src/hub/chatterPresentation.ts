// What a Chatter row says about tone and sources, decided once and in one
// place.
//
// Pure on purpose: every rule here is about wording and proportion, and the
// rules are the part that was wrong on the deployed board. Keeping them out
// of the component means they can be tested against the exact examples the
// design contract names, rather than through a rendered table.
import { sourceLabel } from '../format'
import type { Row, Tone } from '../types'

/* --- tone ---------------------------------------------------------------- */

/** The tone reading, with its denominator made explicit.
 *
 *  B = bullish, S = bearish, U = the neutral residual, D = B + S,
 *  T = D + U. The percentage and the bar share ONE denominator, D, and the
 *  sample line names both D and T so the reader can see how much of the
 *  sample it was computed over.
 *
 *  U is not known neutral sentiment. board.py's `_tones` falls back from a
 *  model attitude to a legacy verdict to a lexicon sign, and a mention that
 *  none of the three placed lands in U alongside a genuinely balanced read.
 *  Folding U into the denominator would turn a handful of directional posts
 *  into a confident-looking number; excluding it silently would hide how
 *  small the directional sample is. So it is excluded AND stated. */
export interface TonePresentation {
  kind: 'directional' | 'undirected' | 'unsampled' | 'unavailable'
  /** The headline. `38.5% bullish`, or a sentence when there is no share. */
  label: string
  /** Bar segments as unrounded fractions of D, or null when there is no bar
   *  to draw. A zero share contributes no segment rather than a hairline. */
  bull: number | null
  bear: number | null
  /** The visible sample line. Descriptive of size, never of confidence. */
  sample: string | null
  /** The full reading, for the accessible detail. Exact counts, and what the
   *  residual actually contains. */
  detail: string
}

/** A count board.py could have produced: a whole, non-negative number.
 *
 *  `Number.isInteger` rejects NaN, Infinity and 1.5; the sign check rejects
 *  -1. A missing or non-numeric value is not coerced to zero, because zero
 *  is a measurement here and "we do not know" is not. */
function counted(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

export function tonePresentation(tone: Tone | null | undefined): TonePresentation {
  if (!tone || !counted(tone.bullish) || !counted(tone.bearish)
      || !counted(tone.neutral)) {
    return {
      kind: 'unavailable',
      label: 'Tone unavailable',
      bull: null,
      bear: null,
      sample: null,
      detail: 'No usable tone counts arrived with this row, so nothing is '
        + 'reported. This is missing information, not a measured zero.',
    }
  }

  const bullish = tone.bullish
  const bearish = tone.bearish
  const residual = tone.neutral
  const directional = bullish + bearish
  const total = directional + residual

  if (total === 0) {
    return {
      kind: 'unsampled',
      label: 'No tone sample',
      bull: null,
      bear: null,
      sample: null,
      detail: 'No eligible mention rows were counted for this company in the '
        + 'selected window, so there is nothing to read a tone from.',
    }
  }

  if (directional === 0) {
    return {
      kind: 'undirected',
      label: 'No directional signal',
      bull: null,
      bear: null,
      sample: `${total} unread or non-directional`,
      detail: `${total} ${total === 1 ? 'signal' : 'signals'} in this sample, `
        + 'none of them bullish or bearish. That covers balanced, mixed or '
        + 'unclear reads together with signals nothing has classified yet. It '
        + 'is not agreement that the outlook is neutral, and it is not a 50/50 '
        + 'split.',
    }
  }

  return {
    kind: 'directional',
    label: `${sharePercent(bullish, directional)} bullish`,
    // Unrounded. The bar is a proportion, and rounding it to match the label
    // would make a 0.4% share draw a visible segment or a 99.6% one leave a
    // visible gap.
    bull: bullish / directional,
    bear: bearish / directional,
    sample: `${directional} directional / ${total} total`,
    detail: `${bullish} bullish, ${bearish} bearish and ${residual} unread or `
      + 'non-directional. The percentage is the bullish share of the '
      + `${directional} directional `
      + `${directional === 1 ? 'signal' : 'signals'} only. The other `
      + `${residual} ${residual === 1 ? 'covers a read that was' : 'cover reads that were'} `
      + 'balanced, mixed or unclear, together with signals nothing has '
      + 'classified yet — not known neutral sentiment. Total means this tone '
      + 'sample of eligible mention rows in the selected window, not every '
      + 'post or person read. '
      // The bar is an approximate indicator, and says so where the exact
      // figures are. A segment below about 2% of the track is drawn wider
      // than its share so it does not vanish -- see `.rh-tonebar` in hub.css.
      + 'Tiny nonzero shares are drawn at a minimum width so they remain '
      + 'visible; use the percentage and counts for the exact balance.',
  }
}

/** One decimal, trailing `.0` trimmed, and never a rounding that lies.
 *
 *  A rounded percentage printing 0% for one bullish post in two hundred was
 *  the specific objection to the old "% positive", and it was a fair one. So
 *  a nonzero share that rounds to zero reads `<0.1%`, and a share below the
 *  whole that rounds to a hundred reads `>99.9%`. A TRUE zero and a TRUE
 *  hundred still print plainly; the sample line is always beside them. */
function sharePercent(part: number, whole: number): string {
  const share = (100 * part) / whole
  const rounded = Math.round(share * 10) / 10
  if (rounded === 0 && part > 0) return '<0.1%'
  if (rounded === 100 && part < whole) return '>99.9%'
  return `${trim(rounded)}%`
}

function trim(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

/* --- sources ------------------------------------------------------------- */

/** One platform, and the concrete feeds under it that counted something. */
export interface Platform {
  /** `reddit`, `bluesky` -- the grouping key, not for display. */
  root: string
  label: string
  /** `r/options`, not `reddit:options`. Named for a reader. */
  feeds: string[]
}

/** What the Sources cell shows, and what its detail holds.
 *
 *  The deployed board joined every concrete feed name through `sourceLabel`
 *  and printed the result, so a ticker seen on thirty subreddits rendered
 *  `Reddit, Reddit, Reddit, ...` across most of the table. The compact form
 *  is the platform count; the concrete identifiers stay reachable rather
 *  than being thrown away. */
export interface SourcePresentation {
  kind: 'unavailable' | 'none' | 'platforms'
  /** `3 platforms`, or a sentence when there is nothing to count. */
  label: string
  /** `Reddit · Bluesky · 4chan /biz/`, or `Reddit · Bluesky +2`. */
  summary: string | null
  platforms: Platform[]
  /** Concrete feeds across every platform. Not the same number as the
   *  platform count, and the detail says which is which. */
  feedCount: number
}

/** Names at most this many platforms in the compact summary before it
 *  switches to `+N`. Three fits the column; a fourth pushes it into the
 *  prose the correction exists to remove. */
const NAMED = 3

export function sourcePresentation(
  active: string[] | null | undefined,
): SourcePresentation {
  if (!Array.isArray(active)) {
    // The field is absent: an older cached board. Reporting `0` would be a
    // measurement nobody made, and falling back to the full `sources` list
    // is the misleading count this replaces.
    return {
      kind: 'unavailable',
      label: 'Source activity unavailable',
      summary: null,
      platforms: [],
      feedCount: 0,
    }
  }

  const platforms = group(active)
  if (!platforms.length) {
    return {
      kind: 'none',
      label: 'No active feeds',
      summary: 'Nothing counted in this sample',
      platforms: [],
      feedCount: 0,
    }
  }

  const feedCount = platforms.reduce((sum, p) => sum + p.feeds.length, 0)
  // Past the cap it names two and counts the rest. The `+N` counts exactly
  // the platforms it did NOT name -- an off-by-one here would be a number
  // the reader can check against the detail and find wrong.
  const shown = platforms.length > NAMED ? 2 : platforms.length
  const hidden = platforms.length - shown
  const named = platforms.slice(0, shown).map((p) => p.label).join(' · ')
  return {
    kind: 'platforms',
    label: `${platforms.length} ${platforms.length === 1 ? 'platform' : 'platforms'}`,
    summary: hidden > 0 ? `${named} +${hidden}` : named,
    platforms,
    feedCount,
  }
}

/** Concrete feed names grouped by their root, busiest platform first.
 *
 *  Two subreddits are ONE platform here, exactly as they are one venue in
 *  `Row.venues`. They share a site, a user population and a rate-limit
 *  budget, so calling them two sources would claim a corroboration that is
 *  not there. */
function group(active: string[]): Platform[] {
  const byRoot = new Map<string, string[]>()
  for (const name of active) {
    if (typeof name !== 'string' || !name) continue
    const root = name.split(':')[0] || name
    const feeds = byRoot.get(root)
    if (feeds) feeds.push(name)
    else byRoot.set(root, [name])
  }
  return Array.from(byRoot, ([root, names]): Platform => ({
    root,
    label: platformLabel(root),
    feeds: names.slice().sort().map(feedLabel),
  })).sort((a, b) => b.feeds.length - a.feeds.length
    || a.label.localeCompare(b.label))
}

/** The platform's own name.
 *
 *  `sourceLabel` falls an unknown key through WHOLE, which is right for a
 *  single feed and wrong for a group heading -- `mastodon:eu` would head a
 *  group that also contains `mastodon:social`. Rooted first, and an unknown
 *  root is capitalised rather than mapped onto a platform it is not. */
function platformLabel(root: string): string {
  const known = sourceLabel(root)
  if (known !== root) return known
  return root.charAt(0).toUpperCase() + root.slice(1)
}

/** A concrete feed, named the way its own community names it. */
export function feedLabel(name: string): string {
  const cut = name.indexOf(':')
  if (cut < 0) return platformLabel(name)
  const root = name.slice(0, cut)
  const rest = name.slice(cut + 1)
  if (!rest) return platformLabel(root)
  if (root === 'reddit') return `r/${rest}`
  return `${platformLabel(root)} · ${rest}`
}

/** The row's active feeds, or undefined when the board predates the field.
 *  One accessor so no caller reaches for `sources` by mistake. */
export function activeSourcesOf(row: Row): string[] | undefined {
  return row.activity_sources
}
