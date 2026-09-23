import { useState, type ReactNode } from 'react'
import type { MatchProposal, SharedConfirmPayload } from './types'
import { CsrfField } from '../csrf'
import { Icon } from '../components/Icon'

/**
 * The follower exercise id `gym_shared_accept` will file this proposal's sets
 * under, or null if none exists yet. Mirrors partners.py's two branches
 * exactly:
 *  - an explicit match posts that candidate's id straight through
 *    (`owned_exercise(value)`);
 *  - "Neu anlegen" is NOT a guaranteed miss -- the server's `'new'` branch
 *    first reuses an owned exercise of the same name
 *    (`my_exercises().filter_by(name=leader_exercise.name)`) and only
 *    creates a fresh row if none exists. `candidates` is documented as
 *    always the full catalogue, so the same name lookup here reproduces
 *    that reuse. Raw equality on purpose: normalising on only one side
 *    would drift from the server's exact `filter_by(name=...)`.
 */
function resolveFollowerExerciseId(proposal: MatchProposal, matchValue: string): number | null {
  if (matchValue !== 'new') {
    return Number(matchValue)
  }
  const reused = proposal.candidates.find(([, name]) => name === proposal.name)
  return reused ? reused[0] : null
}

/** "trainiert seit 12 min", said once at render -- the card is read in the
 *  seconds before a tap, not watched. */
function runningFor(leader: string, startedAt: string | null): string {
  if (startedAt === null) return `${leader} trainiert gerade`
  const minutes = Math.floor((Date.now() - new Date(`${startedAt}Z`).getTime()) / 60000)
  if (minutes < 1) return `${leader} hat gerade angefangen`
  if (minutes < 60) return `${leader} trainiert seit ${minutes} min`
  return `${leader} trainiert seit ${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

interface MatchFieldProps {
  proposal: MatchProposal
  value: string
  onChange: (value: string) => void
  /** Associates a select rendered outside the accept form with it. */
  form?: string
}

function MatchField({ proposal, value, onChange, form }: MatchFieldProps) {
  const id = `match-${proposal.leader_exercise_id}`
  return (
    <div className="field confirm__field">
      <label className="label" htmlFor={id}>{proposal.name}</label>
      <select className="select" id={id} form={form}
        name={`match_${proposal.leader_exercise_id}`}
        value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="new">Als neue Übung anlegen</option>
        {proposal.candidates.map(([candidateId, name]) => (
          <option value={candidateId} key={candidateId}>{name}</option>
        ))}
      </select>
    </div>
  )
}

/**
 * The invite is the page: one lifted card, like the one on Start that led
 * here, naming who is training what and ending in Mitmachen. Seven selects
 * used to stand between the reader and that button, five of them already
 * right and indistinguishable from the two that were not. Now only a leader
 * exercise with no same-named one of your own asks, inside the card and in
 * the attention hue; the rest are confirmed in one line and stay one tap
 * away under "Zuordnung ändern", together with the routine picker.
 */
export function SharedConfirmPage({ payload }: { payload: SharedConfirmPayload }) {
  // Controlled, unlike the original uncontrolled defaultValue: the routine
  // list below counts against the CURRENT selection, so the page has to hold
  // it. The `name` attributes are untouched, so the form still posts exactly
  // what gym_shared_accept has always read.
  const [matches, setMatches] = useState<Record<number, string>>(
    () => Object.fromEntries(payload.proposals.map((proposal) => [
      proposal.leader_exercise_id,
      proposal.exact_id === null ? 'new' : String(proposal.exact_id),
    ])))
  // null means "the reader has not touched it", which is what lets the
  // preselection keep following the matches until they do.
  const [routine, setRoutine] = useState<string | null>(null)

  // number | null per proposal, in payload order. The `!` is safe: `matches`
  // is seeded from these same proposals above and every change to it keys
  // off a `leader_exercise_id` that already exists there, so a lookup can
  // never miss.
  const resolved = payload.proposals.map((proposal) =>
    resolveFollowerExerciseId(proposal, matches[proposal.leader_exercise_id]!))
  const chosen = new Set(resolved.filter((id): id is number => id !== null))
  // The denominator has to count distinct exercises, like the numerator,
  // not proposal rows: if two leader exercises resolve to the SAME one of
  // the follower's own, counting both rows makes `covered === total`
  // unreachable for a routine that genuinely covers everything the
  // follower will perform. Two genuinely-new (null) proposals can't
  // collide -- Exercise is unique per (user_id, name) -- so each null is
  // still one more thing the workout contains.
  const total = chosen.size + resolved.filter((id) => id === null).length
  const rankedAll = payload.templates
    .map((template) => ({
      ...template,
      covered: template.exercise_ids.filter((id) => chosen.has(id)).length,
    }))
    .sort((a, b) => b.covered - a.covered || a.name.localeCompare(b.name, 'de'))
  // Coverage can drop after the reader has already committed to a routine
  // (they change an earlier match, which recomputes `chosen`). Dropping
  // their pick from the list here would leave the controlled <select>
  // holding a value with no matching <option>; the browser silently
  // resets it to the first one, booking the workout under a routine
  // nobody chose. Keeping the explicit pick makes a real zero-coverage
  // state ("0 von 2 Übungen") visible instead of silently swapping it out.
  const ranked = rankedAll
    .filter((template) => template.covered > 0 || String(template.id) === routine)

  // The best-covering routine is preselected when it clearly leads: at least
  // half the workout, and no other routine level with it. Only a PERFECT
  // match used to be, so one exercise the leader added on the way in left
  // the picker on "Keine Routine" -- and the workout filed under nothing.
  // A tie is still the reader's call: picking by name would be a guess.
  const best = ranked[0]
  const clearLead = best !== undefined
    && best.covered * 2 >= total
    && (ranked[1] === undefined || ranked[1].covered < best.covered)
  const autoPick = clearLead ? String(best.id) : ''
  const routineValue = routine ?? autoPick
  const routineName = ranked.find((template) => String(template.id) === routineValue)?.name

  const [open, setOpen] = useState(false)
  const setMatch = (proposal: MatchProposal) => (value: string) =>
    setMatches((current) => ({ ...current, [proposal.leader_exercise_id]: value }))
  // Split on exact_id, not on the current selection: a row the reader has
  // just answered must not jump out of the card under their thumb.
  const asks = payload.proposals.filter((proposal) => proposal.exact_id === null)
  const found = payload.proposals.filter((proposal) => proposal.exact_id !== null)
  const acceptForm = `confirm-accept-${payload.shared_id}`

  let foundLine = ''
  if (found.length > 0 && asks.length === 0) {
    foundLine = found.length === 1
      ? 'Die Übung gibt es bei dir.'
      : `Alle ${found.length} Übungen gibt es bei dir.`
  } else if (found.length > 0) {
    foundLine = found.length === 1
      ? 'Die andere gibt es bei dir.'
      : `Die anderen ${found.length} gibt es bei dir.`
  }

  const card = (children: ReactNode) => (
    <div className="lead confirm">
      <span className="lead__due">{runningFor(payload.leader_name, payload.started_at)}</span>
      <span className="lead__name">{payload.session_name ?? 'Workout'}</span>
      {children}
    </div>
  )

  return (
    <section className="sec confirm-sec" aria-labelledby="sec-confirm">
      <h1 className="sr-only" id="sec-confirm">{`Mit ${payload.leader_name} trainieren`}</h1>

      {payload.refusal !== null ? (
        card(
          <>
            <p className="confirm__refusal">{payload.refusal}</p>
            <a className="btn btn--ghost btn--block confirm__back" href="/gym">Zurück</a>
          </>,
        )
      ) : (
        <>
          <form method="post" action={`/gym/shared/${payload.shared_id}/accept`} id={acceptForm}>
            <CsrfField />
            {card(
              <>
                <p className="lead__list">
                  {payload.proposals.length > 0
                    ? payload.proposals.map((proposal) => proposal.name).join(' · ')
                    : `Noch keine Übungen — sie kommen dazu, sobald ${payload.leader_name} welche anlegt.`}
                </p>

                {asks.length > 0 && (
                  <>
                    <p className="confirm__ask">
                      {asks.length === 1
                        ? 'Eine Übung heißt bei dir anders — welche ist es?'
                        : `${asks.length} Übungen heißen bei dir anders — welche sind es?`}
                    </p>
                    {asks.map((proposal) => (
                      <MatchField key={proposal.leader_exercise_id} proposal={proposal}
                        value={matches[proposal.leader_exercise_id]!}
                        onChange={setMatch(proposal)} />
                    ))}
                  </>
                )}

                {(foundLine !== '' || routineName !== undefined) && (
                  <p className="confirm__ok">
                    {foundLine !== '' && (
                      <span className="confirm__tick" aria-hidden="true">
                        <Icon name="check" />
                      </span>
                    )}
                    <span>
                      {foundLine}
                      {routineName !== undefined && (
                        <>{foundLine !== '' && ' '}Zählt als <b>{routineName}</b>.</>
                      )}
                    </span>
                  </p>
                )}

                {/* Said before the button, not after: the server drops it on
                    accept, and it is the one thing on this page that goes away. */}
                {payload.discards_active && (
                  <p className="confirm__note">
                    Dein laufendes Workout ist noch leer — es wird verworfen.
                  </p>
                )}
                <button type="submit" className="lead__go">Mitmachen</button>
              </>,
            )}
          </form>

          <div className="confirm__foot">
            {/* Absent rather than empty: a disclosure that opens onto nothing
                is worse than silence. */}
            {(found.length > 0 || ranked.length > 0) ? (
              <button type="button" className="confirm__more" aria-expanded={open}
                aria-controls="confirm-more" onClick={() => setOpen((value) => !value)}>
                Zuordnung ändern
                <svg className="confirm__chev" viewBox="0 0 16 16" width="16" height="16"
                  fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
                  strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 3.5l4.5 4.5L6 12.5" />
                </svg>
              </button>
            ) : <span />}
            <form method="post" action={`/gym/shared/${payload.shared_id}/decline`}>
              <CsrfField />
              <button type="submit" className="btn btn--ghost btn--sm">Ablehnen</button>
            </form>
          </div>

          {/* Closed, not unmounted: the matches in here post with the form
              (via `form=`) whether or not the reader ever looks at them. */}
          <div className="confirm__panel" id="confirm-more" hidden={!open}>
            {found.map((proposal) => (
              <MatchField key={proposal.leader_exercise_id} proposal={proposal}
                value={matches[proposal.leader_exercise_id]!}
                onChange={setMatch(proposal)} form={acceptForm} />
            ))}
            {ranked.length > 0 && (
              <div className="field confirm__field">
                <label className="label" htmlFor="confirm-routine">Zählt bei dir als</label>
                <select className="select" id="confirm-routine" name="template_id"
                  form={acceptForm} value={routineValue}
                  onChange={(e) => setRoutine(e.target.value)}>
                  <option value="">Keine Routine</option>
                  {ranked.map((template) => (
                    <option value={template.id} key={template.id}>
                      {`${template.name} — ${template.covered} von ${total} Übungen`}
                    </option>
                  ))}
                </select>
                <p className="sheet__note">
                  Das Workout erscheint auf deinem Start als Durchgang dieser Routine.
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
