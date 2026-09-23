// A disclosure that opens in place.
//
// In place rather than floating: the table scrolls inside its own region, and
// anything absolutely positioned in a cell would be clipped by that scroll
// box. The candidate rail scrolls too. A row that grows while it is open is at
// least honest about what it is showing.
//
// Escape closes it and returns focus to the control that opened it. A reader
// who opened it from the keyboard otherwise has nowhere obvious to go back to.
// Rendered always and hidden with the attribute rather than unmounted, so
// `aria-controls` points at something that exists.
import { useId, useRef, useState } from 'react'

export function Disclosure({ label, trigger, children }: {
  label: string
  trigger: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const button = useRef<HTMLButtonElement>(null)
  return (
    <span
      className="rh-detail"
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !open) return
        // Stopped here so Escape closes THIS and does not travel on to
        // whatever else on the page listens for it -- the navigation menu,
        // and nothing that would change the selected company.
        event.stopPropagation()
        setOpen(false)
        button.current?.focus()
      }}
    >
      <button
        type="button"
        ref={button}
        className="rh-detailtoggle"
        aria-expanded={open}
        aria-controls={id}
        // The visible text LEADS the accessible name, then the label says what
        // opening it does. Replacing the visible text outright failed WCAG
        // 2.5.3 Label in Name: the button read `26 directional / 71 total` and
        // answered to "How KSTR's tone is counted", so a voice-control reader
        // saying "click 26 directional" had no handle on it at all.
        aria-label={`${trigger} — ${label}`}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="rh-sub">{trigger}</span>
      </button>
      <span className="rh-detailbody" id={id} role="group" aria-label={label}
            hidden={!open}>
        {children}
      </span>
    </span>
  )
}
