import { useState } from 'react'
import type { SharedConfirmPayload } from './types'
import { CsrfField } from '../csrf'

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

  // A proposal left on "Neu anlegen" has no id in this catalogue yet, so no
  // routine can contain it: it counts toward the total and can never be
  // covered. That is the honest reading -- the routine really does not have
  // that lift.
  const chosen = new Set(Object.values(matches)
    .filter((value) => value !== 'new').map(Number))
  const total = payload.proposals.length
  const ranked = payload.templates
    .map((template) => ({
      ...template,
      covered: template.exercise_ids.filter((id) => chosen.has(id)).length,
    }))
    .filter((template) => template.covered > 0)
    .sort((a, b) => b.covered - a.covered || a.name.localeCompare(b.name, 'de'))

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
