import type { Market, Selection } from '../types'

const MARKETS: { value: Market; label: string }[] = [
  { value: 'us', label: 'US' },
  { value: 'de', label: 'Germany' },
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
      {MARKETS.map(({ value, label }) => (
        <label key={value}>
          <input type="radio" name="radar-market" value={value}
                 checked={selection.market === value}
                 onChange={() => onChange({ ...selection, market: value })} />
          <span>{label}</span>
        </label>
      ))}
    </fieldset>
  )
}
