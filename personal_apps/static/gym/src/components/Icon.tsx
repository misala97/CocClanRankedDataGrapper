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
  check: <path d="M3.4 8.4l3.2 3.2 6-6.6" />,
  plus: <path d="M8 3.4v9.2M3.4 8h9.2" />,
  chart: (
    <>
      <path d="M2.5 13.5h11" /><path d="M4.5 13.5v-4" />
      <path d="M8 13.5v-8" /><path d="M11.5 13.5v-5.5" />
    </>
  ),
  skip: <><path d="M3.2 3.6l6 4.4-6 4.4z" /><path d="M12.2 3.6v8.8" /></>,
  swap: (
    <>
      <path d="M2.6 5.6h9.2l-2.2-2.2" />
      <path d="M13.4 10.4H4.2l2.2 2.2" />
    </>
  ),
  save: (
    <>
      <path d="M3 3.2h7.4L13 5.8v7h-10z" />
      <path d="M5.4 3.2v3.4h5.2V3.2" /><path d="M5.4 12.8V9.4h5.2v3.4" />
    </>
  ),
  timer: (
    <>
      <circle cx="8" cy="9.2" r="4.8" />
      <path d="M8 6.6v2.6l1.7 1" /><path d="M6.4 1.8h3.2" />
    </>
  ),
  // A bar coming down to the floor: deliberately lighter. Deload carries no
  // hue anywhere in the app, and its icon is as plain as its chip.
  deload: (
    <>
      <path d="M8 2.6v6.2" />
      <path d="M5.4 6.2L8 8.8l2.6-2.6" />
      <path d="M2.8 13.2h10.4" />
    </>
  ),
  bell: (
    <>
      <path d="M12 5.4a4 4 0 0 0-8 0c0 4.4-1.9 5.7-1.9 5.7h11.8S12 9.8 12 5.4" />
      <path d="M9.2 13.7a1.4 1.4 0 0 1-2.4 0" />
    </>
  ),
  trash: (
    <>
      <path d="M2.2 4.4h11.6" />
      <path d="M5.4 4.4V3.1a1.2 1.2 0 0 1 1.2-1.2h2.8a1.2 1.2 0 0 1 1.2 1.2v1.3" />
      <path d="M12.5 4.4l-.6 8.7a1.3 1.3 0 0 1-1.3 1.2H5.4a1.3 1.3 0 0 1-1.3-1.2l-.6-8.7" />
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
