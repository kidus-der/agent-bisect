import { defineConfig } from '@playwright/test'

import baseConfig from './playwright.config'

/** `npm run screenshots`: captures the shell and /gallery for design review. */
export default defineConfig({
  ...baseConfig,
  testMatch: /.*\.shots\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
})
