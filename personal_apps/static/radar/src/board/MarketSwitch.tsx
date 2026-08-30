import type { Market, Selection } from '../types'

/** Shown as US / DE beside the wordmark; announced in full. The short label
 * matches the strip's tab register, the aria-label keeps the accessible name
 * (and the tests that click it) on the unambiguous word. */
const MARKETS: { value: Market; label: string; name: string }[] = [
  { value: 'us', label: 'US', name: 'United States' },
  { value: 'de', label: 'DE', name: 'Germany' },
]

/** Price-market choice only. It deliberately does not alter Radar's Berlin
 * display timezone, the stable social ticker identity, or any other filter. */
export function MarketSwitch({ selection, onChange }: {
  selection: Selection
  onChange: (next: Selection) => void
}) {
  return (
    <fieldset className="market-switch" role="radiogroup" aria-label="Market">
      <legend>Market</legend>
      {MARKETS.map(({ value, label, name }) => (
        <label key={value}>
          <input type="radio" name="radar-market" value={value}
                 aria-label={name}
                 checked={selection.market === value}
                 onChange={() => onChange({ ...selection, market: value })} />
          <span>{label}</span>
        </label>
      ))}
    </fieldset>
  )
}
