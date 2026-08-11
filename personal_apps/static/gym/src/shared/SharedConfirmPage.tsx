import { useState } from 'react'
import type { MatchProposal, SharedConfirmPayload } from './types'
import { CsrfField } from '../csrf'

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

/**
 * Reuses the shared form primitives -- `.field` > `label.label` + `.select`,
 * `.btn.btn--live` for the primary submit and `.btn.btn--ghost` for the
 * secondary -- rather than a parallel set of one-off classes, which is what
 * every other form in Puls does and what keeps this page needing no CSS of
 * its own.
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

  const perfect = ranked.filter((template) => template.covered === total)
  const autoPick = perfect.length === 1 ? String(perfect[0]!.id) : ''
  const routineValue = routine ?? autoPick

  return (
    <section className="sec" aria-labelledby="sec-confirm">
      <div className="sec__head">
        <h2 className="label" id="sec-confirm">{`Mit ${payload.leader_name} trainieren`}</h2>
      </div>

      {payload.refusal !== null ? (
        <>
          <p className="empty">{payload.refusal}</p>
          <a className="btn btn--ghost" href="/gym">Zurück</a>
        </>
      ) : (
        <>
          {/* Exact matches are already resolved and say so. Only the genuinely
              ambiguous ones carry a decision, because asking seven times per
              shared workout would make the common path the annoying one. */}
          <form method="post" action={`/gym/shared/${payload.shared_id}/accept`}>
            <CsrfField />
            {payload.proposals.map((proposal) => (
              <div className="field grow" key={proposal.leader_exercise_id}>
                <label className="label" htmlFor={`match-${proposal.leader_exercise_id}`}>
                  {proposal.name}
                </label>
                <select className="select" id={`match-${proposal.leader_exercise_id}`}
                  name={`match_${proposal.leader_exercise_id}`}
                  value={matches[proposal.leader_exercise_id]}
                  onChange={(e) => setMatches((current) => ({
                    ...current,
                    [proposal.leader_exercise_id]: e.target.value,
                  }))}>
                  <option value="new">Neu anlegen</option>
                  {proposal.candidates.map(([id, name]) => (
                    <option value={id} key={id}>{name}</option>
                  ))}
                </select>
              </div>
            ))}

            {/* Absent rather than empty: a control that can never do anything
                is worse than silence. */}
            {ranked.length > 0 && (
              <div className="field grow">
                <label className="label" htmlFor="confirm-routine">Zählt bei dir als</label>
                <select className="select" id="confirm-routine" name="template_id"
                  value={routineValue}
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

            <button type="submit" className="btn btn--live btn--block">Mitmachen</button>
          </form>

          <form method="post" action={`/gym/shared/${payload.shared_id}/decline`}>
            <CsrfField />
            <button type="submit" className="btn btn--ghost">Ablehnen</button>
          </form>
        </>
      )}
    </section>
  )
}
