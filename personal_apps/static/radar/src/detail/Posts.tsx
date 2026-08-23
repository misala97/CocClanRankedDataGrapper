import { sourceLabel } from '../format'
import type { Post } from '../types'

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
    <>
      <h3>What people are saying · {total} {total === 1 ? 'post' : 'posts'}</h3>
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
                <span className="who">{post.author ?? post.channel}</span>
                <time className="when" dateTime={post.created}>
                  {post.created.slice(11, 16)}
                </time>
                {post.url && (
                  <a className="out" href={post.url} target="_blank"
                     rel="noopener noreferrer">open ↗</a>
                )}
              </div>
              <p>{post.title ? `${post.title} — ` : ''}{post.body}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
