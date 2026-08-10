import type { ReactNode } from 'react'

/**
 * One 16px, currentColor icon set for the whole gym app. Ported from
 * templates/gym/_icon.html -- add cases as later pages need them.
 *
 * Why it exists: the app had no icon set at all, colour emoji were doing the
 * job. An emoji renders in its own vendor palette at its own optical weight,
 * which fights a deliberate type system and cannot inherit a control's state
 * colour. Purely typographic marks (checkmark, multiplication sign, the drag
 * handle's braille dots) are NOT emoji and deliberately stay as text.
 *
 * aria-hidden throughout: every call site supplies its own accessible name on
 * the surrounding <button> / <a>.
 */
const PATHS = {
  back: <path d="M10 3.2L5.2 8l4.8 4.8" />,
  edit: (
    <>
      <path d="M11.3 2.2a1.6 1.6 0 0 1 2.3 2.3l-7.4 7.4-3 .7.7-3z" />
      <path d="M10.2 3.3l2.3 2.3" />
    </>
  ),
  // Filled, stroke-less: three dots drawn as outlines at this size read as
  // rings rather than as a menu mark.
  more: (
    <>
      <circle cx="8" cy="3.4" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="8" cy="12.6" r="1.15" fill="currentColor" stroke="none" />
    </>
  ),
} satisfies Record<string, ReactNode>

export type IconName = keyof typeof PATHS

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className={`icon icon-${name}`} viewBox="0 0 16 16" width="16" height="16"
      fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  )
}
