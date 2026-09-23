import { createContext } from 'react'

/** Whether the server offers the selected-session chart contract
 *  (RADAR_SELECTED_PRICE_CHARTS_ENABLED), read once from the hub's shell.
 *
 *  A rendering hint and nothing more: the chart endpoint refuses by itself when
 *  the flag is off, and whether the server may contact a provider is never sent
 *  to the browser. False outside the hub's provider, so every other consumer of
 *  ChartSection keeps the chart it always drew. */
export const SelectedPriceCharts = createContext(false)
