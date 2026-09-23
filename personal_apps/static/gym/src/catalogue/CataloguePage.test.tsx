import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { CataloguePage } from './CataloguePage'
import type { CatalogueEntry, CataloguePayload } from './types'
import { useCatalogueUi } from './store'

beforeEach(() => {
  useCatalogueUi.setState(useCatalogueUi.getInitialState(), true)
  sessionStorage.clear()
})

const LIST = { default_rest_seconds: 180, weight_increment: 2.5, bar_weight: 20, stack_kg: null }

const entry = (id: number, name: string): CatalogueEntry => ({
  exercise: {
    id, name, muscle_group: 'Brust', is_unilateral: false,
    default_rest_seconds: 180, weight_increment: 2.5, equipment: 'barbell',
    bar_weight: 20, stack_kg: null, secondary_muscle_groups: null, list_defaults: LIST,
  },
  chip_class: null, chip_label: null, last_done: null, best_weight: null,
  last_weight: null, days_ago: null, sessions_since_pr: null,
})

const base: CataloguePayload = {
  groups: [
    { name: 'Brust', entries: [entry(1, 'Bankdrücken (Langhantel)')] },
    { name: 'Beine', entries: [] },
  ],
  open_by_default: true,
}

const mount = (over: Partial<CataloguePayload> = {}) =>
  render(<CataloguePage payload={{ ...base, ...over }} />)

describe('CataloguePage', () => {
  it('lists the lifter\'s exercises and offers nothing to create', () => {
    // One list for everyone: an exercise comes from the add sheet in a
    // workout, never from here.
    const { container } = mount()
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Neue Übung/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/anlegen/i)).not.toBeInTheDocument()
    expect(container.querySelector('dialog')).toBeNull()
  })

  it('points an empty group to the add sheet in a workout', () => {
    mount()
    expect(screen.getByText('keine Übung')).toBeInTheDocument()
    expect(screen.getByText(/Übungen für Beine findest du im Workout unter „Übung hinzufügen“/))
      .toBeInTheDocument()
  })

  it('points an empty catalogue there too, by way of the start page', () => {
    mount({ groups: [{ name: 'Brust', entries: [] }] })
    expect(screen.getByText('Noch keine Übungen')).toBeInTheDocument()
    expect(screen.getByText(/„Übung hinzufügen“/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Auf Start ein Workout beginnen' }))
      .toHaveAttribute('href', '/gym')
  })
})
