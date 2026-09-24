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
    // wrong when it is not: stepping from last week's weight to a very
    // different one is dozens of taps.
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

/**
 * A blank: an exercise with no history is planned with no numbers (V2), so
 * the readout is an empty slot and typing is the way in.
 */
describe('Stepper with no number yet', () => {
  it('shows an empty slot, steps up to its floor, and cannot step down', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { container } = render(<Stepper label="kg" value={null} step={2.5} decimals={1}
      floor={20} ariaLabel="Gewicht eingeben" onChange={onChange} />)
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent(/^$/)
    expect(container.querySelector('.field-num')!.className).toContain('is-blank')
    expect(screen.getByLabelText('Gewicht verringern')).toBeDisabled()

    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenLastCalledWith(20)
  })

  it('opens empty, reports the draft, and Enter commits and moves on', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const onEnter = vi.fn()
    const onDraft = vi.fn()
    render(<Stepper label="kg" value={null} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" enterHint="next"
      onEnter={onEnter} onDraft={onDraft} onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    const entry = screen.getByRole('textbox', { name: 'Gewicht eingeben' })
    expect(entry).toHaveValue('')
    expect(entry).toHaveAttribute('enterkeyhint', 'next')
    await user.type(entry, '42,5')
    expect(onDraft).toHaveBeenLastCalledWith(42.5)

    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(42.5)
    expect(onEnter).toHaveBeenCalledTimes(1)
    expect(onDraft).toHaveBeenLastCalledWith(null)
  })

  it('does not move on from an entry that held no number', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const onEnter = vi.fn()
    render(<Stepper label="kg" value={null} step={2.5} decimals={1}
      ariaLabel="Gewicht eingeben" onEnter={onEnter} onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.keyboard('{Enter}')
    expect(onChange).not.toHaveBeenCalled()
    expect(onEnter).not.toHaveBeenCalled()
  })

  it('takes no rep count below one, typed or stepped', async () => {
    // The server does not take a set of no reps: a 0 would look logged here
    // and stay open there.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="Wdh." value={1} step={1} decimals={0} min={1}
      ariaLabel="Wiederholungen eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Wiederholungen verringern'))
    expect(onChange).toHaveBeenLastCalledWith(1)
    await user.click(screen.getByLabelText('Wiederholungen eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '0{Enter}')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('says why a typed number was not taken, where the label was', async () => {
    // G-070: -10 kg or 0 reps snapped back without a word, so a refusal
    // looked like a missed tap.
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1} max={1000}
      refusedHint="0 bis 1000 kg" ariaLabel="Gewicht eingeben" onChange={onChange} />)

    for (const typed of ['-10', '1000,5', 'abc']) {
      await user.click(screen.getByLabelText('Gewicht eingeben'))
      await user.clear(screen.getByRole('textbox'))
      await user.type(screen.getByRole('textbox'), `${typed}{Enter}`)
      expect(screen.getByText('0 bis 1000 kg')).toBeInTheDocument()
    }
    expect(onChange).not.toHaveBeenCalled()

    // The next step or entry is a fresh start: the label comes back.
    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(screen.getByText('kg')).toBeInTheDocument()
    expect(onChange).toHaveBeenLastCalledWith(22.5)
  })

  it('takes a bound itself, and a cleared entry without comment', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="kg" value={20} step={2.5} decimals={1} max={1000}
      refusedHint="0 bis 1000 kg" ariaLabel="Gewicht eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '{Enter}')
    expect(screen.queryByText('0 bis 1000 kg')).toBeNull()
    await user.click(screen.getByLabelText('Gewicht eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '1000{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(1000)
  })

  it('refuses a rep count that is not a whole number rather than rounding it', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Stepper label="Wdh." value={8} step={1} decimals={0} min={1} max={1000}
      refusedHint="1 bis 1000 Wdh." ariaLabel="Wiederholungen eingeben" onChange={onChange} />)

    await user.click(screen.getByLabelText('Wiederholungen eingeben'))
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '2,5{Enter}')
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText('1 bis 1000 Wdh.')).toBeInTheDocument()
  })
})
