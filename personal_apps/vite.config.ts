/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

// defineConfig comes from vitest/config, not vite: the `test` block below is
// not part of Vite's own config type and fails to type-check against it.
//
// import.meta.url rather than __dirname -- package.json sets "type": "module",
// so this file is ESM and __dirname does not exist in it.
const here = fileURLToPath(new URL('.', import.meta.url))

// One build, one entry per gym page. Steps 2-8 of the spec add their own
// entries here. Output lands in static/gym/dist/ with a manifest that
// vite_assets.py reads for the hashed filenames.
//
// `root` is left at this directory rather than pointed at static/gym/src, so
// that outDir stays inside the root and Vite does not warn about emptying a
// directory outside it. The consequence is that manifest keys are paths
// relative to here -- 'static/gym/src/entries/<name>.tsx' -- which is what
// vite_assets.resolve_asset looks up.
export default defineConfig({
  plugins: [react()],
  base: '/static/gym/dist/',
  build: {
    outDir: resolve(here, 'static/gym/dist'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        exercise: resolve(here, 'static/gym/src/entries/exercise.tsx'),
        session: resolve(here, 'static/gym/src/entries/session.tsx'),
        catalogue: resolve(here, 'static/gym/src/entries/catalogue.tsx'),
        history: resolve(here, 'static/gym/src/entries/history.tsx'),
        start: resolve(here, 'static/gym/src/entries/start.tsx'),
        finished: resolve(here, 'static/gym/src/entries/finished.tsx'),
        statistik: resolve(here, 'static/gym/src/entries/statistik.tsx'),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [resolve(here, 'static/gym/src/test-setup.ts')],
  },
})
