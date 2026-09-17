import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

const THEME_KEY = 'bisect.theme'
const META = { simulated: true, data_source: 'fixture' }
const META_PAYLOAD = {
  ...META,
  package_version: '0.0.0-e2e',
  tau2_commit: 'e2e',
  agent_model: 'e2e-agent',
  user_model: 'e2e-user',
  generated_at: '2026-01-01T00:00:00Z',
}

const NOT_AVAILABLE = { status: 'not_available', reason: 'nothing recorded yet (e2e)' }

function envelope(data: unknown): Record<string, unknown> {
  return { success: true, data, error: null, meta: META }
}

/**
 * The e2e suite owns its API: no dependency on a running `bisect serve`. The
 * list endpoints answer `not_available`, which is what puts the Overview and
 * Runs pages into the designed empty states these tests are about.
 */
async function mockApi(page: Page): Promise<void> {
  await page.route('**/api/meta', (route) => route.fulfill({ json: envelope(META_PAYLOAD) }))
  await page.route('**/api/overview', (route) => route.fulfill({ json: envelope(NOT_AVAILABLE) }))
  await page.route(
    (url) => url.pathname === '/api/runs',
    (route) => route.fulfill({ json: envelope(NOT_AVAILABLE) }),
  )
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('shell loads with navigation, the simulated-data flag and a designed empty state', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link'),
  ).toHaveCount(5)
  await expect(page.getByTestId('simulated-flag')).toBeVisible()
  await expect(page.getByText('bisect eval --split test')).toBeVisible()
})

test('API offline shows the error state and retry recovers', async ({ page }) => {
  await page.unroute('**/api/meta')
  await page.unroute((url) => url.pathname === '/api/runs')
  await page.route('**/api/meta', (route) => route.abort('connectionrefused'))
  // The page's own endpoint has to be down too: that is what it reports on.
  await page.route(
    (url) => url.pathname === '/api/runs',
    (route) => route.abort('connectionrefused'),
  )
  await page.goto('/runs')
  await expect(page.getByRole('alert')).toContainText('Cannot reach the Bisect server')
  await page.unroute('**/api/meta')
  await page.unroute((url) => url.pathname === '/api/runs')
  await mockApi(page)
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByText('bisect record --domain airline --tasks 0-19')).toBeVisible()
})

test('⌘K opens the palette and navigates by keyboard only', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  await page.keyboard.press('ControlOrMeta+k')
  const palette = page.getByRole('dialog', { name: 'Command palette' })
  await expect(palette).toBeVisible()
  await expect(palette.getByRole('combobox')).toBeFocused()
  await page.keyboard.type('live')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/live$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Live' })).toBeVisible()
  await expect(palette).toBeHidden()

  await page.keyboard.press('ControlOrMeta+k')
  await expect(palette).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(palette).toBeHidden()
})

test('navigating moves focus to main and renames the document', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('Overview · Bisect')
  await page
    .getByRole('navigation', { name: 'Primary' })
    .first()
    .getByRole('link', { name: 'Benchmark' })
    .click()
  await expect(page.getByRole('heading', { level: 1, name: 'Benchmark' })).toBeVisible()
  await expect(page.locator('#main')).toBeFocused()
  await expect(page).toHaveTitle('Benchmark · Bisect')
})

test('skip link is the first tab stop and moves focus to main', async ({ page }) => {
  await page.goto('/runs')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.keyboard.press('Tab')
  const skipLink = page.getByRole('link', { name: 'Skip to content' })
  await expect(skipLink).toBeFocused()
  await expect(skipLink).toBeInViewport()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main')).toBeFocused()
})

test('theme toggle switches and persists across reloads, with no flash attribute gap', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('button', { name: 'Switch to light theme' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  expect(await page.evaluate((key) => window.localStorage.getItem(key), THEME_KEY)).toBe('light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  const ground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  expect(ground).toBe('rgb(245, 246, 248)')
})

test('first visit follows prefers-color-scheme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('mobile collapses the top nav into a bottom tab bar', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  const navs = page.getByRole('navigation', { name: 'Primary' })
  await expect(navs).toHaveCount(1)
  await navs.getByRole('link', { name: 'Runs' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('rewind illustration plays and can be paused', async ({ page }) => {
  await page.goto('/gallery')
  const loop = page.getByTestId('rewind-loop')
  await expect(loop).toHaveAttribute('data-phase', 'replay', { timeout: 15_000 })
  await page.getByRole('button', { name: 'Pause' }).click()
  const phase = await loop.getAttribute('data-phase')
  await page.waitForTimeout(2000)
  await expect(loop).toHaveAttribute('data-phase', phase ?? '')
})

test('reduced motion pins the rewind illustration on its final state', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/gallery')
  await expect(page.getByTestId('rewind-loop')).toHaveAttribute('data-phase', 'verdict')
})

for (const theme of ['dark', 'light'] as const) {
  for (const width of [1440, 390] as const) {
    test(`/gallery has no serious or critical axe violations (${theme}, ${width}px)`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
        THEME_KEY,
        theme,
      ] as const)
      await page.goto('/gallery')
      await expect(page.getByRole('heading', { level: 1, name: 'Design gallery' })).toBeVisible()
      // Scroll through once so every lazy chart chunk is mounted before the audit.
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
      await expect(page.getByText('@bklit/sankey-chart')).toBeVisible()
      await page.waitForTimeout(2500)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      )
      expect(overflow, 'no horizontal page overflow').toBeLessThanOrEqual(0)

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
}
