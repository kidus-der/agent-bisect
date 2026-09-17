import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

import { horizontalOverflow, mockP6eApi, applyTheme } from './p6e.fixtures'

const MOBILE = { width: 390, height: 844 } as const
const REGRESSION_CHECK = 'pr-check-00'
const CLEAN_CHECK = 'pr-check-03'

async function openList(page: Page, theme: 'dark' | 'light' = 'dark'): Promise<void> {
  await applyTheme(page, theme)
  await page.goto('/pr-checks')
  await page.getByRole('heading', { level: 1, name: 'PR checks' }).waitFor()
}

async function openDetail(
  page: Page,
  checkId: string,
  theme: 'dark' | 'light' = 'dark',
): Promise<void> {
  await applyTheme(page, theme)
  await page.goto(`/pr-checks/${checkId}`)
  await page.getByText('gate_verdict').waitFor()
}

test('the list separates flagged checks from clean ones', async ({ page }) => {
  await mockP6eApi(page)
  await openList(page)

  await expect(page.getByText('flagged')).toBeVisible()
  await expect(page.getByText('clean').first()).toBeVisible()
  await expect(page.getByRole('link', { name: /#10\d\d/ })).toHaveCount(6)
  await expect(page.locator('[data-verdict="regression"]')).toHaveCount(3)
  await expect(page.locator('[data-verdict="clean"]')).toHaveCount(3)
})

test('a list row opens its detail', async ({ page }) => {
  await mockP6eApi(page)
  await openList(page)

  await page.getByRole('link', { name: '#1000' }).click()

  await expect(page).toHaveURL(new RegExp(`/pr-checks/${REGRESSION_CHECK}$`))
  await expect(page.getByText('Regression detected').first()).toBeVisible()
})

test('the detail states base against head with intervals and a p value', async ({ page }) => {
  await mockP6eApi(page)
  await openDetail(page, REGRESSION_CHECK)

  await expect(page.getByText('87.5%')).toBeVisible()
  await expect(page.getByText('[69.0%, 95.7%]')).toBeVisible()
  await expect(page.getByText('58.3%')).toBeVisible()
  await expect(page.getByText('[38.8%, 75.5%]')).toBeVisible()
  await expect(page.getByText('−29.2 pts')).toBeVisible()
  await expect(page.getByText('0.023').first()).toBeVisible()
})

test('the detail shows the decisive step on each ref', async ({ page }) => {
  await mockP6eApi(page)
  await openDetail(page, REGRESSION_CHECK)

  await expect(page.getByRole('heading', { name: 'Where the blame rule lands' })).toBeVisible()
  await expect(page.getByText('unchanged')).toBeVisible()
  await expect(page.getByText('The same step is decisive on both refs.')).toBeVisible()
})

test('the detail renders the PR comment preview and can copy it', async ({ page }) => {
  await mockP6eApi(page)
  await openDetail(page, REGRESSION_CHECK)

  await expect(page.getByText('bisect-bot')).toBeVisible()
  await expect(page.getByText('#1000')).toBeVisible()
  await expect(page.getByText('Bisect · agent regression detected')).toBeVisible()
  await expect(page.getByText('decisive step')).toBeVisible()
  await expect(page.getByRole('button', { name: /copy markdown/i })).toBeVisible()
})

test('the scenario table lists every scenario with its change', async ({ page }) => {
  await mockP6eApi(page)
  await openDetail(page, REGRESSION_CHECK)

  const table = page.getByRole('table', { name: /Pass rate per scenario/ })
  await expect(table).toBeVisible()
  await expect(page.getByText('24 of 24 worse on head')).toBeVisible()
})

test('a clean check reports no regression and no decisive step', async ({ page }) => {
  await mockP6eApi(page)
  await openDetail(page, CLEAN_CHECK)

  await expect(page.getByText('No regression').first()).toBeVisible()
  // With neither ref decisive the panel collapses to that one line.
  await expect(page.getByText('No step was decisive on either ref.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Where the blame rule lands' })).toHaveCount(0)
})

test('an unmeasured gate is reported, never filled in with numbers', async ({ page }) => {
  await mockP6eApi(page, { unmeasured: true })
  await applyTheme(page, 'dark')
  await page.goto('/pr-checks')

  await expect(page.getByText(/pr checks · not measured/i)).toBeVisible()
  await expect(page.getByText('no gate results yet')).toBeVisible()
  await expect(page.getByText('bisect gate --base main --head HEAD')).toBeVisible()
})

test('neither view scrolls sideways at 390px', async ({ page }) => {
  await mockP6eApi(page)
  await page.setViewportSize(MOBILE)

  await openList(page)
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)

  await openDetail(page, REGRESSION_CHECK)
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)
})

for (const theme of ['dark', 'light'] as const) {
  test(`has no serious or critical axe violations in ${theme}`, async ({ page }) => {
    await mockP6eApi(page)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openDetail(page, REGRESSION_CHECK, theme)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = results.violations.filter((violation) =>
      ['serious', 'critical'].includes(violation.impact ?? ''),
    )
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])
  })
}
