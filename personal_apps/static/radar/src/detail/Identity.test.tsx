import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Identity } from './Identity'
import { detail } from '../fixtures'
import type { Detail } from '../types'

const identity: Detail['identity'] = { ...detail('NVDA').identity, name: 'NVIDIA Corp' }

describe('the panel\'s watch button', () => {
  it('offers to watch, and to stop', async () => {
    const toggle = vi.fn()
    const { rerender } = render(<Identity identity={identity} watching={false} onToggleWatch={toggle} />)

    await userEvent.click(screen.getByRole('button', { name: 'Watch NVDA' }))
    expect(toggle).toHaveBeenCalledTimes(1)

    rerender(<Identity identity={identity} watching onToggleWatch={toggle} />)
    expect(screen.getByRole('button', { name: 'Stop watching NVDA' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('shows no button without an account to mark for', () => {
    render(<Identity identity={identity} />)
    expect(screen.queryByRole('button', { name: /watch/i })).toBeNull()
  })
})
