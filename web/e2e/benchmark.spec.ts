import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

import { horizontalOverflow, mockP6eApi, applyTheme } from './p6e.fixtures'

const MOBILE = { width: 390, height: 844 } as const

async function openBenchmark(page: Page, theme: 'dark' | 'light' = 'dark'): Promise<void> {
  await applyTheme(page, theme)
  await page.goto('/benchmark')
  await page
    .getByRole('heading', { level: 2, name: 'Which method blames the right step' })
    .waitFor()
}

test('the method comparison names every method with its interval and its cost', async ({
  page,
}) => {
  await mockP6eApi(page)
  await openBenchmark(page)

  await expect(page.getByText('96.5%').first()).toBeVisible()
  // Twice: on the Bisect row, and in the compact one-line verdict for narrow
  // viewports, which is in the DOM at every width.
  await expect(page.getByText('[90.2%, 98.8%]').first()).toBeVisible()
  await expect(page.getByText('$1.56').first()).toBeVisible()
  await expect(page.getByText('780 calls').first()).toBeVisible()
  // The pre-registered bar is reported at its real value, above 100%.
  await expect(page.getByText(/not met · 102\.2%/)).toBeVisible()
  await expect(page.getByText(/pre-registered bar 102\.2%/)).toBeVisible()
})

test('the accuracy matrix draws every cell and swaps to a table', async ({ page }) => {
  await mockP6eApi(page)
  await openBenchmark(page)

  const matrix = page.locator('[data-slot="accuracy-matrix"]')
  await expect(matrix).toBeVisible()
  // 4 fault types x 5 methods, each printing its own value.
  await expect(matrix.locator('[data-slot="matrix-cell"]')).toHaveCount(20)

  await page.getByRole('radio', { name: 'Matrix' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(matrix).toHaveCount(0)
  await expect(page.getByRole('table').first()).toBeVisible()
})

test('the sankey, the ablation and the cost histogram all render', async ({ page }) => {
  await mockP6eApi(page)
  await openBenchmark(page)

  await expect(page.getByRole('heading', { name: 'Where the blame landed' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What snapshots are worth' })).toBeVisible()
  await expect(page.getByText('+10.5 pts')).toBeVisible()
  await expect(page.getByText('95% CI [+1.9 pts, +19.6 pts]')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What a diagnosis costs' })).toBeVisible()
  await expect(page.locator('svg').filter({ hasText: 'model calls' })).toBeVisible()
})

test('switching the cost method moves the labelled mean marker', async ({ page }) => {
  await mockP6eApi(page)
  await openBenchmark(page)

  const histogram = page.locator('svg').filter({ hasText: 'model calls' })
  await expect(histogram.getByText(/Bisect · 780 calls/)).toBeVisible()

  // The control is a real radio group, so arrow keys move the selection.
  await page.getByRole('radio', { name: 'bisect' }).focus()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')

  await expect(histogram.getByText(/Re-run live · 1,540 calls/)).toBeVisible()
  await expect(histogram.getByText(/Bisect · 780 calls/)).toHaveCount(0)
})

test('the dataset filters down and links into a run', async ({ page }) => {
  await mockP6eApi(page)
  await openBenchmark(page)
  const table = page.getByRole('table', {
    name: /Labelled failures: one planted fault per recorded run/,
  })
  await expect(table).toBeVisible()

  await page.getByLabel('fault type').selectOption('tool_error')
  await expect(page.getByText(/^\d+ shown ·/)).toBeVisible()
  const chips = table.getByText('tool error text')
  await expect(chips.first()).toBeVisible()
  await expect(table.getByText('wrong value')).toHaveCount(0)

  const firstRun = table.getByRole('link').first()
  const runId = (await firstRun.textContent()) ?? ''
  await firstRun.click()
  await expect(page).toHaveURL(new RegExp(`/runs/${runId.trim()}$`))
})

test('the search filter can empty the table without breaking it', async ({ page }) => {
  await mockP6eApi(page)
  await openBenchmark(page)

  await page.getByLabel('search').fill('no-such-run')
  await expect(page.getByText('no rows match')).toBeVisible()

  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(page.getByRole('table', { name: /Labelled failures/ })).toBeVisible()
})

test('an unmeasured benchmark is reported, never filled in with numbers', async ({ page }) => {
  await mockP6eApi(page, { unmeasured: true })
  await applyTheme(page, 'dark')
  await page.goto('/benchmark')

  await expect(page.getByText(/benchmark · not measured/i)).toBeVisible()
  await expect(page.getByText('no eval results yet (data/eval.parquet not found)')).toBeVisible()
  await expect(page.getByText('bisect eval --split test')).toBeVisible()
  await expect(page.getByText('96.5%')).toHaveCount(0)
})

test('the page does not scroll sideways at 390px', async ({ page }) => {
  await mockP6eApi(page)
  await page.setViewportSize(MOBILE)
  await openBenchmark(page)
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)
})

for (const theme of ['dark', 'light'] as const) {
  test(`has no serious or critical axe violations in ${theme}`, async ({ page }) => {
    await mockP6eApi(page)
    // Reduced motion pins every entrance on its final frame; axe would
    // otherwise sample text mid-fade and report it as low contrast.
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openBenchmark(page, theme)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = results.violations.filter((violation) =>
      ['serious', 'critical'].includes(violation.impact ?? ''),
    )
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])
  })
}
