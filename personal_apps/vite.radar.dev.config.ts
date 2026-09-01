import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The radar board with hot reload, for design iteration (impeccable live
// mode) -- not a build. `vite.radar.config.ts` stays the build: its base is
// the dist URL Flask serves, which is wrong for a dev server, and one config
// cannot be both.
//
// The page is static/radar/dev.html at http://localhost:5174/static/radar/dev.html.
// Everything the island asks the server for is proxied to the Flask dev
// server on :5001 -- the API, and the login the API redirects to. Cookies are
// per host, not per port, so a session signed in at :5001 is sent here too.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/radar/api': 'http://localhost:5001',
      '/login': 'http://localhost:5001',
      '/logout': 'http://localhost:5001',
    },
  },
})
