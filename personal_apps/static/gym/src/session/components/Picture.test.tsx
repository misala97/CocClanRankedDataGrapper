import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Drawing, PictureTile, movementOf } from './Picture'

const SRC = '/static/gym/art/bankdruecken.webp?v=0123abcd'

describe('PictureTile', () => {
  it('shows the drawing, sized before it arrives, and stays out of the reading order', () => {
    const { container } = render(<PictureTile src={SRC} size="live" />)
    const tile = container.querySelector('.pic.pic--live')!
    expect(tile.getAttribute('aria-hidden')).toBe('true')
    const img = tile.querySelector('img')!
    expect(img.getAttribute('src')).toBe(SRC)
    expect(img.getAttribute('alt')).toBe('')
    expect([img.getAttribute('width'), img.getAttribute('height')]).toEqual(['640', '640'])
    expect(img.hasAttribute('loading')).toBe(false)
  })

  it('loads a queue tile only when it nears the screen', () => {
    const { container } = render(<PictureTile src={SRC} size="queue" />)
    expect(container.querySelector('.pic--queue img')!.getAttribute('loading')).toBe('lazy')
  })

  it('draws the dumbbell for an exercise without a drawing yet', () => {
    const { container } = render(<PictureTile src={null} size="queue" />)
    const tile = container.querySelector('.pic.pic--queue.pic--none')!
    expect(tile.querySelector('img')).toBeNull()
    expect(tile.querySelector('svg.icon-dumbbell')).not.toBeNull()
  })
})

describe('movementOf', () => {
  it('names the movement a drawing shows, not the list entry', () => {
    // I1b review: one drawing per movement for now -- Bankdrücken's shows the
    // dumbbells, so "Zeichnung: Bankdrücken (Langhantel)" would say otherwise.
    expect(movementOf('Bankdrücken (Langhantel)')).toBe('Bankdrücken')
    expect(movementOf('Trizepsstrecken über Kopf (Kabel, Seil)')).toBe('Trizepsstrecken über Kopf')
    expect(movementOf('Eigene Übung')).toBe('Eigene Übung')
  })
})

describe('Drawing', () => {
  it('carries the words it is given', () => {
    const { container } = render(<Drawing src={SRC} alt="Zeichnung: Bankdrücken" />)
    expect(container.querySelector('img')!.getAttribute('alt')).toBe('Zeichnung: Bankdrücken')
  })
})
