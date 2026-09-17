import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { RECORDED, mockApi } from './apiFixture'

const THEME_KEY = 'bisect.theme'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('the hero leads with the result, in points, at display size', async ({ page }) => {
  await page.goto('/')
  const headline = page.getByRole('heading', { level: 1 })
  await expect(headline).toContainText('+9.3 pts')
  const fontSize = await headline.evaluate((node) => getComputedStyle(node).fontSize)
  expect(fontSize, 'the hero uses the 44px display size').toBe('44px')
})

test('both methods are shown with their own 95% intervals', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Bisect', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Judge · step by step' })).toBeVisible()
  await expect(page.getByText('95% CI 90.2% – 98.8%')).toBeVisible()
  await expect(page.getByText('95% CI 78.5% – 92.7%')).toBeVisible()
})

test('the gap is reported without an interval, and says so', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/no interval is reported for the gap itself/i)).toBeVisible()
})

test('simulated data is admitted in the hero, not just in the top bar', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/numbers are simulated/i)).toBeVisible()
  await expect(page.getByTestId('simulated-flag')).toBeVisible()
})

test('every KPI reaches its recorded value', async ({ page }) => {
  await page.goto('/')
  // InstrumentLabel appends a trailing underscore, so match the label itself.
  for (const label of ['runs recorded', 'failures diagnosed', 'calls spent', 'cost per diagnosis'])
    await expect(page.getByText(new RegExp(`^${label}_$`))).toBeVisible()
  await expect(page.getByText(String(RECORDED.kpis.runs_recorded)).first()).toBeVisible()
})

test('both charts carry a text alternative with their real numbers', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/Recall at m, for m from 1 to 10/)).toBeAttached()
  await expect(page.getByText(/cost on a logarithmic axis/)).toBeAttached()
  await expect(page.getByText(/Bisect: \$1\.56 per diagnosis/)).toBeAttached()
})

test('the rewind plays the hero run and can be paused', async ({ page }) => {
  await page.goto('/')
  const loop = page.getByTestId('rewind-loop')
  // It only plays while on screen, which is the point of the pause rule.
  await loop.scrollIntoViewIfNeeded()
  await expect(loop).toBeVisible()
  await expect(page.getByText(`rewind · ${RECORDED.heroRunId}`)).toBeVisible()
  await expect(loop).toHaveAttribute('data-phase', 'rewind', { timeout: 20_000 })

  await page.getByRole('button', { name: 'Pause' }).click()
  const paused = await loop.getAttribute('data-phase')
  await page.waitForTimeout(2000)
  await expect(loop).toHaveAttribute('data-phase', paused ?? '')
  await expect(page.getByRole('button', { name: 'Play' })).toHaveAttribute('aria-pressed', 'true')
})

test('reduced motion pins the rewind on its verdict, with no pause control', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  const loop = page.getByTestId('rewind-loop')
  await loop.scrollIntoViewIfNeeded()
  await expect(loop).toHaveAttribute('data-phase', 'verdict')
  await expect(page.getByRole('button', { name: 'Pause' })).toHaveCount(0)
  // Blame never appears without its measured effect.
  await expect(page.getByText('+0.88').first()).toBeVisible()
})

test('the rewind opens its run', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.getByRole('link', { name: 'Open run' }).scrollIntoViewIfNeeded()
  await page.getByRole('link', { name: 'Open run' }).click()
  await expect(page).toHaveURL(new RegExp(`/runs/${RECORDED.heroRunId}$`))
})

test('the runs strip leads to the full list', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'View all' }).scrollIntoViewIfNeeded()
  await page.getByRole('link', { name: 'View all' }).click()
  await expect(page).toHaveURL(/\/runs$/)
})

test('an unmeasured Overview shows the command that would measure it', async ({ page }) => {
  await page.route('**/api/overview', (route) =>
    route.fulfill({
      json: {
        success: true,
        data: { status: 'not_available', reason: 'no evaluation yet' },
        error: null,
        meta: { simulated: false, data_source: 'real' },
      },
    }),
  )
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  await expect(page.getByText('bisect eval --split test')).toBeVisible()
})

test('an unreachable API shows the error state and retry recovers', async ({ page }) => {
  await page.unroute('**/api/overview')
  await page.route('**/api/overview', (route) => route.abort('connectionrefused'))
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('Cannot reach the Bisect server')
  await page.unroute('**/api/overview')
  await mockApi(page)
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('+9.3 pts')
})

test('390px lays out without scrolling sideways', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(500)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow, 'no horizontal page overflow').toBeLessThanOrEqual(0)
})

for (const theme of ['dark', 'light'] as const) {
  test(`Overview has no serious or critical axe violations (${theme})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
      THEME_KEY,
      theme,
    ] as const)
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await page.waitForTimeout(1500)

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze()
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    )
    expect(
      blocking.map(
        (violation) =>
          `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`,
      ),
    ).toEqual([])
  })
}
