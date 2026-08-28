import { useState } from 'react'

import { count, sourceLabel } from '../format'
import type { Post } from '../types'

/** Past this, one post has stopped being a quote and become the page.
 *
 *  Measured rather than guessed: a 4chan copypasta pasted into this zone ran
 *  past thirty screen-heights and buried the twenty-four posts under it, which
 *  is the opposite of what the zone is for. The clamp is on the rendered text
 *  rather than a character cut, so the decision is made at the width the post
 *  is actually read at. */
const CLAMP_LINES = 7

function Body({ post }: { post: Post }) {
  const [open, setOpen] = useState(false)
  const text = `${post.title ? `${post.title} — ` : ''}${post.body ?? ''}`
  // The cheapest honest signal that there is more: the clamp itself cannot be
  // measured without a layout pass, and one long post is common enough that a
  // per-post measurement is not worth a resize observer. Characters over-
  // estimate a wrapped line, so the control appears slightly late rather than
  // on a post that was never clipped.
  const long = text.length > CLAMP_LINES * 90

  return (
    <>
      <p className={open || !long ? undefined : 'clamp'}>{text}</p>
      {long && (
        <button type="button" className="more" aria-expanded={open}
                onClick={() => setOpen(!open)}>
          {open ? 'Show less' : 'Show the whole post'}
        </button>
      )}
    </>
  )
}

/** What people actually said.
 *
 *  The zone that lets a reader form their own view instead of trusting the
 *  score. No aggregate substitutes for it: a filing, a squeeze, a pump and ten
 *  bots repeating each other all produce the same mention count, and you can
 *  usually tell them apart in five seconds of reading.
 *
 *  Links open in a new tab with `noopener` -- these are arbitrary URLs from
 *  arbitrary strangers, and handing them a window reference is a way for a
 *  page nobody vetted to navigate this one.
 */
export function Posts({ posts, total, retentionNote }: {
  posts: Post[]
  total: number
  retentionNote?: boolean
}) {
  return (
    <section className="zone">
      <h3>What people are saying
        <span className="q">
          · {count(total)} {total === 1 ? 'post' : 'posts'}, newest first
        </span>
      </h3>
      {posts.length === 0 ? (
        <p className="below">
          Nothing in this window.
          {retentionNote && ' Posts are kept for 30 days.'}
        </p>
      ) : (
        <ul className="posts">
          {posts.map((post, index) => (
            <li className="post" key={`${post.source}-${post.created}-${index}`}>
              <div className="phead">
                <span className="src">{sourceLabel(post.source)}</span>
                {/* Handles have no length limit anywhere upstream, and a long
                    one used to push the outbound link off the row. It
                    truncates and keeps its full value for a hover. */}
                <span className="who" title={post.author ?? post.channel}>
                  {post.author ?? post.channel}
                </span>
                <time className="when" dateTime={post.created}>
                  {post.created.slice(11, 16)}
                </time>
                {post.url && (
                  <a className="out" href={post.url} target="_blank"
                     rel="noopener noreferrer">open ↗</a>
                )}
              </div>
              <Body post={post} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
