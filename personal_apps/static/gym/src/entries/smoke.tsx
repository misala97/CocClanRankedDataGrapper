// Proves the toolchain end to end: TSX compiles, React mounts, the hashed
// bundle resolves through vite_asset(). Deleted in Task 6 once a real entry
// exists.
import { createRoot } from 'react-dom/client'

const el = document.getElementById('gym-root')
if (el) {
  createRoot(el).render(<p data-testid="smoke">ok</p>)
}
