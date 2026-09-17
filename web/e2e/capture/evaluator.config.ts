import { defineConfig, devices } from '@playwright/test'

/**
 * Config for the independent design evaluator's capture pass.
 *
 * Unlike `playwright.config.ts` it starts no web server: the evaluator drives
 * the REAL app against the REAL fixture API, so the two processes are started
 * by hand and this config only points at them.
 *
 *   uv run python -m agent_bisect.server --fixture --port 8490
 *   cd web && BISECT_API_ORIGIN=http://127.0.0.1:8490 npx vite --port 5190
 *   cd web && EVAL_ROUND=1 npx playwright test --config e2e/capture/evaluator.config.ts
 */
const BASE_URL = process.env.EVAL_BASE_URL ?? 'http://127.0.0.1:5190'

export default defineConfig({
  testDir: '.',
  testMatch: /evaluator-capture\.ts/,
  fullyParallel: true,
  workers: 4,
  timeout: 120_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    video: process.env.EVAL_VIDEO === '1' ? 'on' : 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
