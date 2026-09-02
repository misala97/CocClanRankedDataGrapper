import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Posts } from './Posts'
import type { Post } from '../types'

const post = (over: Partial<Post>): Post => ({
  source: 'bluesky', author: 'ann', channel: 'firehose', created: '2026-09-02T14:00:00Z',
  title: null, body: 'to the moon', url: null, tone: 'bullish', judged_by: 'model', ...over,
})

describe('who judged a post', () => {
  it('prints Claude for the model, wording for the lexicon, nothing when unscored', () => {
    const { container } = render(<Posts total={3} posts={[
      post({ author: 'ann', judged_by: 'model' }),
      post({ author: 'bob', judged_by: 'lexicon', tone: 'bearish' }),
      post({ author: 'cy', judged_by: null, tone: 'neutral' }),
    ]} />)

    const labels = Array.from(container.querySelectorAll('.post')).map(
      (card) => card.querySelector('.pby')?.textContent ?? '')
    expect(labels).toEqual(['Claude', 'wording', ''])
    expect(screen.getByText('Claude')).toHaveClass('pby')
  })
})
