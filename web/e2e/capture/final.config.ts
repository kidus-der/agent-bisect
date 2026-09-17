import { defineConfig, devices } from '@playwright/test'

/**
 * Config for `final-capture.ts` (P6 gate curated screenshots). No `webServer`:
 * the gate script starts `bisect serve --fixture` itself and this only points
 * at it -- see final-capture.ts's module docstring.
 */
const BASE_URL = process.env.FINAL_BASE_URL ?? 'http://127.0.0.1:8500'

export default defineConfig({
  testDir: '.',
  testMatch: /final-capture\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: BASE_URL },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
