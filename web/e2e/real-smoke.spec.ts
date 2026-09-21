/**
 * P6 real-data finalization: a data-source-agnostic smoke + axe pass
 * against `bisect serve --real` serving the production build. Unlike
 * the P6 gate's own e2e suite (playwright.gate.config.ts), this makes no
 * assertion on specific fixture values -- real recordings have a
 * different run count, different run ids, and a dev-split (not test-split)
 * benchmark result (docs/gates/P5.md). It exists to catch a page that
 * crashes, hangs on "not available" where data exists, or fails
 * accessibility against the real API, not to re-run the fixture-mode gate.
 *
 *   uv run bisect serve --real --port 8498
 *   cd web && REAL_E2E_PORT=8498 REAL_RUN_ID=<a diagnosed run> \
 *     REAL_PR_CHECK_ID=<a real gate check id> \
 *     npx playwright test --config playwright.real.config.ts
 */
import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

const RUN_ID = process.env.REAL_RUN_ID ?? ''
const PR_CHECK_ID = process.env.REAL_PR_CHECK_ID ?? ''

const PAGES: readonly string[] = [
  '/',
  '/runs',
  `/runs/${RUN_ID}`,
  '/benchmark',
  '/live',
  '/pr-checks',
  `/pr-checks/${PR_CHECK_ID}`,
]

async function noBlockingAxeViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze()
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
}

/** Charts and entrance animations settle after first paint (see final-capture.ts) --
 * axe must sample resting colors, not an in-flight transition. */
const SETTLE_MS = 2200

for (const path of PAGES) {
  test(`${path || '/'} loads real data with no crash and no blocking axe violations`, async ({
    page,
  }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(String(error)))

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    // No React error boundary, no thrown render error.
    await expect(page.getByText(/something went wrong/i)).toHaveCount(0)
    expect(pageErrors, pageErrors.join('\n')).toEqual([])
    await page.waitForTimeout(SETTLE_MS)

    const violations = await noBlockingAxeViolations(page)
    expect(violations, violations.join('\n')).toEqual([])
  })
}

test('data source flag reads Recorded data, not Simulated', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('simulated-flag')).toHaveCount(0)
  await expect(page.getByText('Recorded')).toBeVisible()
})

test('overview headline names the dev split as a diagnostic run', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('results-split-notice')).toContainText('diagnostic')
})
