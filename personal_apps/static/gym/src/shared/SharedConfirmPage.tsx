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
                  defaultValue={proposal.exact_id === null
                    ? 'new' : String(proposal.exact_id)}>
                  <option value="new">Neu anlegen</option>
                  {proposal.candidates.map(([id, name]) => (
                    <option value={id} key={id}>{name}</option>
                  ))}
                </select>
              </div>
            ))}
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
