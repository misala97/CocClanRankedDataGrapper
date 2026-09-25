/** "1 Übung", "12 Übungen". */
export const uebungen = (count: number) => `${count} ${count === 1 ? 'Übung' : 'Übungen'}`

/** A band's size, or while searching its hits of it: "3 von 12". */
export const bandCount = (hits: number, size: number, searching: boolean) =>
  searching ? `${hits} von ${size}` : uebungen(size)

/** An id from a group's name: "Ohne Muskelgruppe" as an IDREF was two. */
export const slug = (name: string) => name.replace(/\s+/g, '-')

/**
 * A group's band on Übungen, the same device Verlauf uses for months -- one
 * list language. An h3: the parts ("Deine", "Noch nie gemacht") are the h2s.
 */
export function Band({ id, name, count, expanded, onToggle }: {
  id: string
  name: string
  count: string
  expanded: boolean
  onToggle(): void
}) {
  return (
    <h3 className="group__h">
      <button type="button"
        className={expanded ? 'group uebungen-group-header is-open' : 'group uebungen-group-header'}
        id={id} aria-expanded={expanded} onClick={onToggle}>
        <svg className="group__chev" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="3" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M9 5l7 7-7 7" />
        </svg>
        <span className="label">{name}</span>
        <span className="start__sp" />
        <span className="label">{count}</span>
      </button>
    </h3>
  )
}
