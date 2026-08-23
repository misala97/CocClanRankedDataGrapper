import { sourceLabel } from '../format'
import type { Breakdown as BreakdownData } from '../types'

/** The chatter, taken apart.
 *
 *  `Loudest account` is the reason this section exists. One account posting
 *  forty times reads as forty mentions everywhere else on the surface, and no
 *  other figure the board computes exposes that.
 *
 *  Bull and bear are counts in words, never a coloured bar. Green and red mean
 *  price direction on this surface and nothing else -- a green/red tone bar
 *  has been built and removed twice for exactly that collision.
 */
export function Breakdown({ breakdown, windowHours }: {
  breakdown: BreakdownData
  windowHours: number
}) {
  const b = breakdown
  return (
    <>
      <h3>Chatter breakdown · last {windowHours} hours</h3>
      <div className="bd">
        <div>
          <table>
            <thead>
              <tr>
                <th>Venue</th>
                <th className="r">Mentions</th>
                <th className="r">Voices</th>
                <th className="r">Share</th>
              </tr>
            </thead>
            <tbody>
              {b.venues.map((venue) => (
                <tr key={venue.source}>
                  <td className="venue">{sourceLabel(venue.source)}</td>
                  <td className="r">{venue.mentions}</td>
                  <td className="r">{venue.voices}</td>
                  <td className="r">
                    {b.mentions
                      ? `${Math.round(venue.mentions / b.mentions * 100)}%`
                      : '—'}
                  </td>
                </tr>
              ))}
              {b.venues.length === 0 && (
                <tr><td colSpan={4} className="venue">
                  Nothing in this window.
                </td></tr>
              )}
            </tbody>
          </table>

          {b.mentions > 0 && (
            <p className="wording">
              <span><b>{b.bullish}</b> bullish</span>
              <span><b>{b.bearish}</b> bearish</span>
              {/* Not padding. Most mentions carry no lexicon word at all, and
                  hiding them turns a handful of scored posts into a
                  confident-looking sentiment reading. */}
              <span className="q">
                <b>{b.neutral}</b> carried no wording at all
              </span>
            </p>
          )}
        </div>

        <div>
          <Stat label="Loudest account's share"
                value={share(b.top_author_share)}
                warn={(b.top_author_share ?? 0) >= 0.3} />
          <Stat label="Top two accounts" value={share(b.top_two_share)}
                warn={(b.top_two_share ?? 0) >= 0.4} />
          <Stat label="Peak hour" value={
            b.peak_hour
              ? `${b.peak_hour.slice(11, 16)} · ${b.peak_count}/h`
              : '—'} />
          <Stat label="First ever seen" value={b.first_seen ?? 'never'} />
          <Stat label="Distinct voices" value={String(b.voices)} />
        </div>
      </div>
    </>
  )
}

function Stat({ label, value, warn }: {
  label: string
  value: string
  warn?: boolean
}) {
  return (
    <div className="stat">
      <span className="k">{label}</span>
      <span className={warn ? 'v warn' : 'v'}>{value}</span>
    </div>
  )
}

function share(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}
