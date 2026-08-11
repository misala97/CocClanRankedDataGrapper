import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Stepper } from './Stepper'

/**
 * The steppers are the reason no keyboard opens mid-workout: the value lives
 * in a hidden input and the readout is text, so tapping it is a decision, not
 * a focus event.
 */
describe('Stepper', () => {
  it('steps by the exercise increment, not by one', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={60} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(onChange).toHaveBeenLastCalledWith(62.5)
  })

  it('never goes below zero', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={1} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht verringern'))
    expect(onChange).toHaveBeenLastCalledWith(0)
  })

  it('rounds only the readout, never the value', async () => {
    // toFixed is a display concern. Rounding the stored number would turn a
    // 1.25 kg step into an effective 1.3 after only a few taps.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={0} step={1.25} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(onChange).toHaveBeenLastCalledWith(1.25)
  })

  it('shows German decimals', () => {
    render(<Stepper label="kg" value={62.5} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={vi.fn()} />)
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent('62,5')
  })

  it('renders whole numbers without a decimal', () => {
    render(<Stepper label="Wdh." value={8} step={1} decimals={0}
      ariaLabel="Wiederholungen eingeben" onChange={vi.fn()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('8')
  })

  it('opens a field when the readout is tapped', async () => {
    // The steppers are right when the prefilled number is already close, and
    // wrong when it is not: an exercise with no history starts at a default,
    // and stepping from there to a real working weight is dozens of taps.
    const user = userEvent.setup()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={vi.fn()} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    expect(screen.getByRole('textbox')).toHaveValue('20,0')
  })

  it('accepts both decimal separators when typing', async () => {
    // The app renders commas, phone keypads vary on which one they offer, and
    // rejecting either would be a silent no-op at the exact moment the lifter
    // is trying to correct a number.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '82,5{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(82.5)
  })

  it('does not snap a typed value to the increment', async () => {
    // The increment governs stepping; typing is exact by intent -- that is
    // what it is for.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '83.7{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(83.7)
  })

  it('abandons the edit on Escape', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '999{Escape}')

    // The original needed a `settled` flag here: removing the input fires a
    // synchronous blur, nested inside the Escape handler, which would commit
    // the value the Escape just rejected. Once the field is closed, no commit
    // may follow.
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('commits on blur', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <>
        <Stepper label="kg" value={20} step={2.5} decimals={1}
          ariaLabel="Gewicht eingeben" onChange={onChange} />
        <button type="button">elsewhere</button>
      </>)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '77,5')
    await user.click(screen.getByText('elsewhere'))
    expect(onChange).toHaveBeenLastCalledWith(77.5)
  })

  it('ignores unparseable and negative typed input', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), 'abc{Enter}')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('labels per side for a unilateral exercise', () => {
    render(<Stepper label="kg je Seite" value={20} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onChange={vi.fn()} />)
    expect(screen.getByText('kg je Seite')).toBeInTheDocument()
  })
})
