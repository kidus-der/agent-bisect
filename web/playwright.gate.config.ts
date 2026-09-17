import { defineConfig } from '@playwright/test'

import baseConfig from './playwright.config'

/**
 * P6 gate: runs the same specs as `playwright.config.ts` against the
 * production build served by `bisect serve --fixture` (BISECT_E2E_PORT),
 * not the Vite dev server -- this is what a user actually gets. The gate
 * script starts and stops `bisect serve` itself, so there is no `webServer`
 * block here; unlike `evaluator.config.ts` (which points a dev-server pair
 * at a separate fixture API), this points straight at the one process that
 * serves both the static bundle and `/api/*`.
 *
 *   uv run bisect serve --fixture --port 8500
 *   cd web && BISECT_E2E_PORT=8500 npx playwright test --config playwright.gate.config.ts
 */
const HOST = '127.0.0.1'
const E2E_PORT = Number(process.env.BISECT_E2E_PORT ?? 5183)
const BASE_URL = `http://${HOST}:${E2E_PORT}`

export default defineConfig({
  ...baseConfig,
  use: { ...baseConfig.use, baseURL: BASE_URL },
  reporter: [
    ['list'],
    ['json', { outputFile: process.env.BISECT_E2E_JSON ?? '../runs/p6/e2e-report.json' }],
  ],
  webServer: undefined,
})
