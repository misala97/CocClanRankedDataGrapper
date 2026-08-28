import { MARK_WHY, rankTerm } from '../format'
import type { Mark, Row, Session } from '../types'

/** What the marks on this board mean.
 *
 *  PRODUCT.md is explicit that the marks are load-bearing rather than
 *  metadata, and that hiding one would let a reader act on a number the system
 *  already knows is unreliable. The rows honoured half of that: they printed
 *  `· no-print · warming-up` and nothing anywhere on the surface said what
 *  either one was. The sentences existed -- MARK_WHY has been written since
 *  the marks were added -- and were never rendered by anything.
 *
 *  A glossary rather than a hover. `title` is mouse-only, and the reader most
 *  likely to need the sentence is the one who has just seen an unfamiliar word
 *  on a row; a definition they have to discover by pointing at it is a
 *  definition for people who already know it. This is also the only version
 *  that a keyboard or a screen reader reaches at all.
 *
 *  Scoped to the marks actually on the board, and only the ones the rows still
 *  carry: a mark the header has taken over is explained up there instead, and
 *  repeating it here would define the same word twice on one screen.
 */
export function Marks({ rows, suppress, session }: {
  rows: Row[]
  suppress: readonly Mark[]
  /** Decides which quantity the board is ordered by, and therefore which
   *  term this glossary has to define. */
  session: Session
}) {
  const ranked = rankTerm(session)
  const shown = (Object.keys(MARK_WHY) as Mark[]).filter(
    (mark) => !suppress.includes(mark)
      && rows.some((row) => row.marks.includes(mark)))

  return (
    <div className="below marks">
      {/* The ranking quantity, defined once. It is printed at the end of
          every row and nothing on the surface said what it was -- the same
          gap the marks had, on the number the whole board is ordered by. */}
      <dl className="rank">
        <div>
          <dt>{ranked.label}</dt>
          <dd>{ranked.why}</dd>
        </div>
      </dl>
      {shown.length > 0 && (
        <p className="sub">What the marks on these rows mean</p>
      )}
      <dl>
        {shown.map((mark) => (
          <div key={mark}>
            <dt>{mark}</dt>
            <dd>{MARK_WHY[mark]}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
