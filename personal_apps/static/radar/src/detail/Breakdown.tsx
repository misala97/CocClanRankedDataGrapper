import { count, dayStamp, formatMarketTime, sourceLabel } from '../format'
import type { Breakdown as BreakdownData } from '../types'

/** Above these, one or two accounts are carrying the whole thing and the
 *  number stops describing a crowd. Shared with the wording below so the
 *  amber and the sentence can never disagree about what is going on. */
const LOUD_ONE = 0.3
const LOUD_TWO = 0.4

/** The chatter, taken apart.
 *
 *  Two columns split by KIND, not into "the table" and "whatever is left".
 *  Concentration is the reason this section exists -- one account posting
 *  forty times reads as forty mentions everywhere else on the surface, and no
 *  other figure the board computes exposes that -- so it gets its own column
 *  and a sentence saying what the share means. As row four of five identical
 *  stats it read like trivia.
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
  const one = b.top_author_share
  const two = b.top_two_share

  return (
    <section className="zone" aria-labelledby="zone-breakdown">
      <h3 id="zone-breakdown">Chatter breakdown <span className="q">· last {windowHours} hours</span></h3>
      <div className="bd">
        <div>
          <table>
            <thead>
              <tr>
                <th scope="col">Venue</th>
                <th className="r" scope="col">Mentions</th>
                <th className="r" scope="col">Voices</th>
                <th className="r" scope="col">Share</th>
              </tr>
            </thead>
            <tbody>
              {b.venues.map((venue) => (
                <tr key={venue.source}>
                  <th scope="row" className="venue">{sourceLabel(venue.source)}</th>
                  <td className="r">{count(venue.mentions)}</td>
                  <td className="r">{count(venue.voices)}</td>
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
              <span><b>{count(b.bullish)}</b> bullish</span>
              <span><b>{count(b.bearish)}</b> bearish</span>
              {/* Not padding. Most mentions carry no lexicon word at all, and
                  hiding them turns a handful of scored posts into a
                  confident-looking sentiment reading. */}
              <span className="q">
                <b>{count(b.neutral)}</b> carried no wording at all
              </span>
              {/* Both scores are kept precisely so this comparison is
                  possible -- a post the word list and the model read
                  opposite ways is a post that was being sarcastic. Words,
                  not colour: green and red mean price direction here and
                  nothing else. */}
              {b.disagreements > 0 && (
                <span className="q">
                  <b>{count(b.disagreements)}</b> flagged for review by
                  local/model disagreement
                </span>
              )}
            </p>
          )}

          {/* The facts that are only facts, kept out of the column beside so
              that column stays five lines about one thing. */}
          <p className="plain">
            {b.peak_hour
              ? <>Peak hour <b>{formatMarketTime(b.peak_hour)}</b> at{' '}
                  <b>{count(b.peak_count)}</b> mentions · </>
              : null}
            <b>{count(b.voices)}</b> distinct {b.voices === 1 ? 'voice' : 'voices'}
            {b.first_seen
              ? <> · first ever seen on <b>{dayStamp(b.first_seen)}</b></>
              : null}
          </p>
        </div>

        <div>
          <p className="sub">How concentrated it is</p>
          <Stat label="Loudest account’s share" value={share(one)}
                warn={(one ?? 0) >= LOUD_ONE} />
          <Stat label="Top two accounts" value={share(two)}
                warn={(two ?? 0) >= LOUD_TWO} />
          <Concentration one={one} two={two} voices={b.voices} />
        </div>
      </div>
    </section>
  )
}

/** What the share means, in a sentence, either way round.
 *
 *  A number the reader has to threshold in their head is a number they will
 *  skip. This says which of the two situations they are looking at without
 *  ever saying what to do about it -- PRODUCT.md's scope boundary holds here
 *  as much as anywhere.
 */
function Concentration({ one, two, voices }: {
  one: number | null
  two: number | null
  voices: number
}) {
  if (one === null) return null

  if (one >= LOUD_ONE || (two ?? 0) >= LOUD_TWO) {
    return (
      <p className="note">
        {Math.round(one * 100)}% of this came from a single account.
        {' '}{count(voices)} {voices === 1 ? 'voice' : 'voices'} saying it once is
        a different fact than one account saying it {count(voices)} times.
      </p>
    )
  }
  return (
    <p className="note">
      No single account is carrying this — the loudest of {count(voices)}{' '}
      {voices === 1 ? 'voice' : 'voices'} is under a third of it.
    </p>
  )
}

function Stat({ label, value, warn }: {
  label: string
  value: string
  warn?: boolean
}) {
  return (
    <div className={warn ? 'stat hot' : 'stat'}>
      <span className="k">{label}</span>
      <span className="v">{value}</span>
    </div>
  )
}

function share(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}
