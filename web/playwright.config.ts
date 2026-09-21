import { defineConfig, devices } from '@playwright/test'

const HOST = '127.0.0.1'
// A dedicated port so e2e never collides with a running `npm run dev` (5173).
// Agents sharing this checkout run suites at the same time: BISECT_E2E_PORT gives each its own server.
const E2E_PORT = Number(process.env.BISECT_E2E_PORT ?? 5183)
const BASE_URL = `http://${HOST}:${E2E_PORT}`

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  // real-smoke.spec.ts only makes sense against `bisect serve --real`
  // (playwright.real.config.ts) -- it needs REAL_RUN_ID/REAL_PR_CHECK_ID
  // and real recordings, neither of which this fixture-backed config has.
  testIgnore: /real-smoke\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: BASE_URL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npx vite --host ${HOST} --port ${E2E_PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
