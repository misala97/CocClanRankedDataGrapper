/** The way out of a short board, worded once.
 *
 *  Three places tell the reader the same thing -- the empty list, the account
 *  of what was excluded, and the empty panel -- and they had drifted into
 *  three sentences naming the controls three ways: "widen the window",
 *  "a longer Score window", "switch to All", "switch the segment to All". Two
 *  of them appeared on screen together, six inches apart, which reads as two
 *  different suggestions rather than one.
 *
 *  The wording names the controls as they are LABELLED, because the reader
 *  has to find them: the summary line says 4h and the views row says All.
 *  (It said "Score window" until 2026-09-01; no control had carried that
 *  word since the 2026-08-30 strip.)
 */
export function Widen({ tail = '.' }: { tail?: string }) {
  return (
    <>Try a longer <b>window</b>, or the <b>All</b> view{tail}</>
  )
}
