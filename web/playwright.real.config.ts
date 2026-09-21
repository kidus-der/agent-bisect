import { defineConfig } from '@playwright/test'

import baseConfig from './playwright.config'

/**
 * Real-mode e2e + axe smoke, run once against the production build served
 * by `bisect serve --real` -- the P6 real-data finalization's counterpart
 * to playwright.gate.config.ts (which runs the full fixture-mode gate
 * suite). Only real-smoke.spec.ts runs here; the gate's own specs assert
 * on fixture-specific values that real recordings do not have.
 *
 *   uv run bisect serve --real --port 8498
 *   cd web && REAL_E2E_PORT=8498 REAL_RUN_ID=<run> REAL_PR_CHECK_ID=<id> \
 *     npx playwright test --config playwright.real.config.ts
 */
const HOST = '127.0.0.1'
const E2E_PORT = Number(process.env.REAL_E2E_PORT ?? 8498)
const BASE_URL = `http://${HOST}:${E2E_PORT}`

export default defineConfig({
  ...baseConfig,
  testMatch: /real-smoke\.spec\.ts/,
  testIgnore: undefined,
  use: { ...baseConfig.use, baseURL: BASE_URL },
  // Outside runs/ deliberately: this P6 real-data pass must not write
  // anywhere under runs/ (another agent owns that tree while it runs).
  reporter: [
    ['list'],
    ['json', { outputFile: process.env.REAL_E2E_JSON ?? '../docs/gates/p6-real-e2e-report.json' }],
  ],
  webServer: undefined,
})
