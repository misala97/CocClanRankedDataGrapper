import { useMemo, useState } from 'react'
import type { CatalogueEntry, CataloguePayload, SortMode } from './types'
import { fold, recency, sincePr } from './format'
import { kg1 } from '../format'
import { useCatalogueUi } from './store'
import { useSheets } from '../session/stores'
import { Icon } from '../components/Icon'
import { NewExerciseSheet } from './NewExerciseSheet'
import { postFormData, MutationFailed } from '../api'
import { morphFrom } from '../vt'

const SORTS: { mode: SortMode; label: string }[] = [
  { mode: 'muscle', label: 'Muskelgruppe' },
  { mode: 'stall', label: 'Ohne PR' },
  { mode: 'recent', label: 'Zuletzt' },
]

function ExerciseRow({ entry, group, isNew }: {
  entry: CatalogueEntry
  group: string
  isNew: boolean
}) {
  const stall = sincePr(entry.sessions_since_pr)
  const meta = recency(entry.days_ago) + (stall ? ` · ${stall}` : '')

  return (
    // The whole row is the link. The two figures used to sit outside it, so
    // link-list navigation announced the name and never the weight.
    <a className={`row row--top uebungen-row${isNew ? ' is-new' : ''}`}
      href={`/gym/exercises/${entry.exercise.id}`}
      onClick={morphFrom('ex', '.nameline__n')}
      data-group={group}>
      <span className="row__main stack">
        <span className="nameline">
          <span className="nameline__n">{entry.exercise.name}</span>
          {entry.chip_label !== null && (
            <span className={`vtag vtag--${entry.chip_class}`}>{entry.chip_label}</span>
          )}
        </span>
        <span className="row__meta">{meta}</span>
      </span>
      {/* Leads with the weight you would put on the bar today. It led with the
          all-time best, unlabelled -- so a row reading "15,0 kg" could not be
          told apart from a working weight. */}
      <span className="row__trail row__trail--stack">
        {entry.last_weight !== null ? (
          <>
            {/* "je Seite" on unilateral lifts. Without it the catalogue -- the
                one surface whose job is comparing exercises -- showed a
                per-side load above a bilateral one, which is the same weight
                read as half. */}
            <span className="vol">
              {kg1(entry.last_weight)}
              <small>{entry.exercise.is_unilateral ? 'kg/Seite' : 'kg'}</small>
            </span>
            <span className="lastline">
              {entry.best_weight !== null && entry.best_weight > entry.last_weight
                ? `zuletzt · best ${kg1(entry.best_weight)}`
                : 'zuletzt'}
            </span>
          </>
        ) : (
          <span className="vol vol--none">—</span>
        )}
      </span>
    </a>
  )
}

export function CataloguePage({ payload: initial }: { payload: CataloguePayload }) {
  const query = useCatalogueUi((s) => s.query)
  const setQuery = useCatalogueUi((s) => s.setQuery)
  const sort = useCatalogueUi((s) => s.sort)
  const setSort = useCatalogueUi((s) => s.setSort)
  const isOpen = useCatalogueUi((s) => s.isOpen)
  const toggleGroup = useCatalogueUi((s) => s.toggleGroup)
  const openSheet = useSheets((s) => s.open)
  const closeSheet = useSheets((s) => s.close)
  // Creating an exercise answers with the fresh catalogue: added_id
  // highlights the new row, name_taken raises the banner -- exactly what the
  // ?added= / ?name_taken=1 redirects delivered, minus the reload.
  const [payload, setPayload] = useState(initial)
  const [saveError, setSaveError] = useState<string | null>(null)

  const createExercise = async (fields: FormData): Promise<boolean> => {
    try {
      const fresh = await postFormData<CataloguePayload>('/gym/exercises/add', fields)
      setPayload(fresh)
      setSaveError(null)
      // Closed on the collision too: the redirect flow closed it (the page
      // reloaded), and the banner explains itself in page context.
      closeSheet()
      return !fresh.name_taken
    } catch (error) {
      setSaveError(error instanceof MutationFailed
        ? error.germanMessage
        : 'Speichern fehlgeschlagen.')
      return false
    }
  }

  const total = payload.groups.reduce((n, g) => n + g.entries.length, 0)
  const needle = fold(query.trim())
  const groupNames = payload.groups.map((g) => g.name)

  // Every row with the group it belongs to, folded once rather than per
  // keystroke. The search matches the group name too, so "Beine" finds them.
  const rows = useMemo(
    () => payload.groups.flatMap((g) => g.entries.map((entry) => ({
      entry, group: g.name, fold: fold(`${entry.exercise.name} ${g.name}`),
    }))),
    [payload.groups])

  const hits = needle === '' ? rows : rows.filter((r) => r.fold.includes(needle))

  const flat = useMemo(() => {
    const compareStall = (a: typeof rows[number], b: typeof rows[number]) =>
      (b.entry.sessions_since_pr ?? -1) - (a.entry.sessions_since_pr ?? -1)
    const compareRecent = (a: typeof rows[number], b: typeof rows[number]) =>
      (b.entry.last_done ?? '').localeCompare(a.entry.last_done ?? '')
    return [...hits].sort(sort === 'recent' ? compareRecent : compareStall)
  }, [hits, sort])

  return (
    // No wrapper: the mount node in uebungen.html already IS .uebungen.
    <>
      <header className="verlauf__head">
        <h1 className="verlauf__h">Übungen</h1>
        {/* aria-live: search rewrites this, and it used to sit at 17 while
            four rows showed. */}
        <span className="verlauf__count" aria-live="polite">{hits.length}</span>
        <span className="start__sp" />
        <button type="button" className="verlauf__act"
          onClick={() => openSheet('sheet-new-exercise')}>
          <Icon name="plus" />
          Neue Übung
        </button>
      </header>

      {saveError !== null && (
        <p className="flash flash--error" role="alert">{saveError}</p>
      )}
      {payload.name_taken && (
        <section className="next-time">
          <div className="next-time__lbl">Nicht gespeichert</div>
          <p className="next-time__body">Eine Übung mit diesem Namen gibt es schon.</p>
        </section>
      )}

      {total > 0 ? (
        <>
          <div className="searchbar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
            </svg>
            <input type="search" id="uebungen-search" className="searchbar__input"
              placeholder="Übung suchen…" autoComplete="off"
              aria-label="Übungen durchsuchen"
              value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>

          <div className="sorts" role="group" aria-label="Sortierung">
            {SORTS.map(({ mode, label }) => (
              <button key={mode} type="button"
                className={sort === mode ? 'sort is-on' : 'sort'}
                aria-pressed={sort === mode}
                onClick={() => setSort(mode)}>{label}</button>
            ))}
          </div>

          {hits.length === 0 && (
            <p className="empty" role="status">
              Keine Übung gefunden für <b>{query.trim()}</b>.{' '}
              <button type="button" className="linklike"
                onClick={() => setQuery('')}>Suche zurücksetzen</button>
            </p>
          )}

          <div id="uebungen-list" className={sort === 'muscle' ? undefined : 'is-flat'}>
            {sort === 'muscle'
              ? payload.groups.map((group) => {
                const groupHits = hits.filter((r) => r.group === group.name)
                // A searching reader wants the matches, not their folders, so
                // a query opens every band that has one and hides the rest.
                const expanded = needle !== ''
                  ? groupHits.length > 0
                  : isOpen(group.name, payload.open_by_default)
                if (needle !== '' && groupHits.length === 0) return null

                return (
                  <section className="group-sec" key={group.name}
                    aria-labelledby={`g-${group.name}`}>
                    {group.entries.length > 0 ? (
                      <h2 className="group__h">
                        <button type="button"
                          className={expanded ? 'group uebungen-group-header is-open' : 'group uebungen-group-header'}
                          id={`g-${group.name}`} aria-expanded={expanded}
                          onClick={() => toggleGroup(
                            group.name, payload.open_by_default, groupNames)}>
                          <svg className="group__chev" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                            strokeLinejoin="round" aria-hidden="true">
                            <path d="M9 5l7 7-7 7" />
                          </svg>
                          <span className="label">{group.name}</span>
                          <span className="start__sp" />
                          <span className="label">
                            {needle !== ''
                              ? `${groupHits.length} von ${group.entries.length}`
                              : `${group.entries.length} ${group.entries.length === 1 ? 'Übung' : 'Übungen'}`}
                          </span>
                        </button>
                      </h2>
                    ) : (
                      /* A group with nothing in it is the strongest signal
                         this page can give a planner. It is NOT a toggle:
                         there is nothing behind it, and a disclosure that
                         opens onto nothing is a worse lie than none. */
                      <>
                        <h2 className="group__h">
                          <span className="group group--empty" id={`g-${group.name}`}>
                            <span className="label">{group.name}</span>
                            <span className="start__sp" />
                            <span className="label">keine Übung</span>
                          </span>
                        </h2>
                        <p className="group__none">
                          Lege hier eine Übung an, um die Gruppe zu trainieren.
                        </p>
                      </>
                    )}

                    {expanded && groupHits.map(({ entry }) => (
                      <ExerciseRow key={entry.exercise.id} entry={entry}
                        group={group.name}
                        isNew={payload.added_id === entry.exercise.id} />
                    ))}
                  </section>
                )
              })
              : flat.map(({ entry, group }) => (
                <ExerciseRow key={entry.exercise.id} entry={entry} group={group}
                  isNew={payload.added_id === entry.exercise.id} />
              ))}
          </div>
        </>
      ) : (
        <section className="uebungen-blank">
          <h2 className="uebungen-blank__title">Noch keine Übungen</h2>
          <p className="uebungen-blank__body">
            Übungen gehören dir allein — deine Namen, deine Gewichtsschritte. Leg die
            erste an, oder füge sie unterwegs im Workout hinzu; sie bleibt dann hier.
          </p>
          <button type="button" className="btn btn--live"
            onClick={() => openSheet('sheet-new-exercise')}>
            <Icon name="plus" />
            Erste Übung anlegen
          </button>
        </section>
      )}

      <NewExerciseSheet muscleGroups={payload.muscle_groups}
        equipmentLabels={payload.equipment_labels}
        defaultRestSeconds={payload.default_rest_seconds}
        onCreate={createExercise} />
    </>
  )
}
