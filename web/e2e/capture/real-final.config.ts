import { defineConfig, devices } from '@playwright/test'

/**
 * Config for `real-final-capture.ts` (P6 real-data finalization's curated
 * screenshots). No `webServer`: the caller starts `bisect serve --real`
 * itself and this only points at it -- see real-final-capture.ts's module
 * docstring.
 */
const BASE_URL = process.env.REAL_FINAL_BASE_URL ?? 'http://127.0.0.1:8498'

export default defineConfig({
  testDir: '.',
  testMatch: /real-final-capture\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: BASE_URL },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
