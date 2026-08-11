/// <reference types="vite/client" />

// Gives TypeScript Vite's import suffixes -- `?raw` in particular, which
// stores.test.ts uses to read a module's own source and assert it does not
// import the server payload types. Without this the test runs fine (Vite
// resolves it) while `tsc --noEmit` fails, which is a split worth not having.
