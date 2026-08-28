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
 *  has to find them: the strip says Score and it says All.
 */
export function Widen({ tail = '.' }: { tail?: string }) {
  return (
    <>Try a longer <b>Score</b> window, or the <b>All</b> segment{tail}</>
  )
}
