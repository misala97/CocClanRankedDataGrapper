/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

// Radar's own build, separate from vite.config.ts on purpose.
//
// One config cannot emit two outDirs, and the alternative -- pointing both
// features at a single shared dist -- was rejected: gym's service worker
// caches its dist by path prefix (static/gym/sw.js), so radar's chunks would
// be precached for a page that never loads them, and every radar rebuild
// would invalidate gym's cache.
//
// `root` stays at this directory for the same reason it does in the gym
// config: outDir has to live inside the root or Vite warns on every build.
// The consequence is the manifest key format vite_assets.resolve_asset
// expects -- 'static/radar/src/entries/<name>.tsx'.
const here = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  base: '/static/radar/dist/',
  build: {
    outDir: resolve(here, 'static/radar/dist'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        board: resolve(here, 'static/radar/src/entries/board.tsx'),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['static/radar/src/**/*.test.{ts,tsx}'],
    setupFiles: [resolve(here, 'static/radar/src/test-setup.ts')],
    // Off by default, and with it off vitest stubs every `.css` import -- the
    // stub catches `radar.css?raw` too, so motion.test.ts received an empty
    // string and its assertions passed vacuously in both directions. On, the
    // `?raw` import returns the file. Nothing else here imports CSS, so this
    // costs one file read per run.
    css: true,
  },
})
