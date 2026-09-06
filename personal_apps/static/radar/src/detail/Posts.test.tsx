import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Posts } from './Posts'
import type { Post } from '../types'

const post = (over: Partial<Post>): Post => ({
  source: 'bluesky', author: 'ann', channel: 'firehose', created: '2026-09-02T14:00:00Z',
  title: null, body: 'to the moon', url: null, tone: 'bullish', judged_by: 'model',
  judged_label: 'Claude', ...over,
})

const labelsIn = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('.post')).map(
    (card) => card.querySelector('.pby')?.textContent?.trim() ?? '')

describe('who judged a post', () => {
  it('names the model, says wording for the lexicon, nothing when unscored', () => {
    const { container } = render(<Posts total={3} posts={[
      post({ author: 'ann', judged_by: 'model', judged_label: 'Claude' }),
      post({ author: 'bob', judged_by: 'lexicon', judged_label: null, tone: 'bearish' }),
      post({ author: 'cy', judged_by: null, judged_label: null, tone: 'neutral' }),
    ]} />)

    expect(labelsIn(container)).toEqual(['Claude', 'wording', ''])
    expect(screen.getByText('Claude')).toHaveClass('pby')
  })

  // The name is the SERVER'S answer, not the component's. It was a literal
  // 'Claude' here, which stopped being true the moment a second backend
  // could write tone.
  it('prints whichever model the server named', () => {
    const { container } = render(<Posts total={1} posts={[
      post({ judged_by: 'model', judged_label: 'model' }),
    ]} />)

    expect(labelsIn(container)).toEqual(['model'])
  })

  it('falls back to a generic name rather than guessing one', () => {
    const { container } = render(<Posts total={1} posts={[
      post({ judged_by: 'model', judged_label: null }),
    ]} />)

    expect(labelsIn(container)).toEqual(['model'])
  })
})
