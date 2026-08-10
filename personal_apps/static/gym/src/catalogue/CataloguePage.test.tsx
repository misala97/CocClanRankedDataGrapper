import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CataloguePage } from './CataloguePage'
import type { CatalogueEntry, CataloguePayload } from './types'
import { useCatalogueUi } from './store'
import { useSheets } from '../session/stores'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useCatalogueUi.setState(useCatalogueUi.getInitialState(), true)
  sessionStorage.clear()
})

const entry = (id: number, name: string): CatalogueEntry => ({
  exercise: {
    id, name, muscle_group: 'Brust', is_unilateral: false,
    default_rest_seconds: null, weight_increment: null, equipment: null,
    bar_weight: null, stack_kg: null, secondary_muscle_groups: null,
  },
  chip_class: null, chip_label: null, last_done: null, best_weight: null,
  last_weight: null, days_ago: null, sessions_since_pr: null,
})

const base: CataloguePayload = {
  groups: [{ name: 'Brust', entries: [entry(1, 'Bankdrücken')] }],
  muscle_groups: ['Brust', 'Rücken'],
  equipment_labels: { stack: 'Stack-Maschine', dumbbell: 'Kurzhantel' },
  open_by_default: true,
  default_rest_seconds: 150,
  added_id: null,
  name_taken: false,
}

const mount = (over: Partial<CataloguePayload> = {}) =>
  render(<CataloguePage payload={{ ...base, ...over }} />)

/** Fill the one required field and submit the create sheet. */
async function create(name: string) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /Neue Übung/ }))
  await user.type(screen.getByLabelText('Name'), name)
  await user.click(screen.getByRole('button', { name: 'Hinzufügen' }))
  return user
}

describe('creating an exercise in place', () => {
  it('posts the form, closes the sheet and highlights the new row', async () => {
    const fresh: CataloguePayload = {
      ...base,
      groups: [{ name: 'Brust', entries: [entry(1, 'Bankdrücken'), entry(9, 'Dips')] }],
      added_id: 9,
    }
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => fresh,
    } as unknown as Response)))

    const { container } = mount()
    await create('Dips')

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/gym/exercises/add')
    expect((init.body as FormData).get('name')).toBe('Dips')

    expect(await screen.findByText('Dips')).toBeInTheDocument()
    expect(container.querySelector('.uebungen-row.is-new')).toHaveTextContent('Dips')
    // A closed <dialog> drops out of the accessibility tree entirely.
    expect(container.querySelector('dialog#sheet-new-exercise')).not.toHaveAttribute('open')
    vi.unstubAllGlobals()
  })

  it('raises the collision banner from the answer instead of a reload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => ({ ...base, name_taken: true }),
    } as unknown as Response)))

    mount()
    await create('Bankdrücken')
    expect(await screen.findByText('Eine Übung mit diesem Namen gibt es schon.'))
      .toBeInTheDocument()
    // Not cleared: after a collision you reopen to fix the name, not to
    // retype everything.
    expect(screen.getByLabelText('Name')).toHaveValue('Bankdrücken')
    vi.unstubAllGlobals()
  })

  it('states a failure and keeps the sheet', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    mount()
    await create('Dips')
    expect(await screen.findByRole('alert')).toHaveTextContent('Verbindung fehlgeschlagen')
    expect(screen.getByRole('dialog')).toHaveAttribute('open')
    vi.unstubAllGlobals()
  })
})
