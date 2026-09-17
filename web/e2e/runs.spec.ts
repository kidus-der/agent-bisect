import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { RECORDED, mockApi } from './apiFixture'

const THEME_KEY = 'bisect.theme'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('lists the recorded runs with their marks', async ({ page }) => {
  await page.goto('/runs')
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  await expect(page.getByText(`${RECORDED.runTotal} runs`)).toBeVisible()

  const first = page.getByRole('row').nth(1)
  await expect(first.getByText(RECORDED.firstRunId)).toBeVisible()
  await expect(first.getByRole('img', { name: /^tokens per step/ })).toBeVisible()
  await expect(first.getByRole('img', { name: /^Effect per step/ })).toBeVisible()
})

test('a filter narrows the list, lands in the URL and survives a reload', async ({ page }) => {
  await page.goto('/runs')
  // The radio itself is sr-only (focusable, announced); the label is what is clicked.
  await page.getByText('✕ Fail').click()

  await expect(page).toHaveURL(/outcome=fail/)
  // Only what was chosen: no query string full of defaults.
  await expect(page).not.toHaveURL(/dir=/)
  // The <output> element, not the table's sr-only caption.
  const summary = page.locator('output')
  const narrowed = await summary.textContent()

  await page.reload()
  await expect(page.getByRole('radio', { name: '✕ Fail' })).toBeChecked()
  await expect(summary).toHaveText(narrowed ?? '')
  // The pill itself, not any cell containing the letters "pass".
  await expect(page.locator('[data-outcome="pass"]')).toHaveCount(0)
})

test('a fault-type filter narrows further and clears again', async ({ page }) => {
  await page.goto('/runs')
  const request = page.waitForRequest((call) => call.url().includes('fault_type=stale_record'))
  await page.getByRole('button', { name: /more filters/i }).click()
  await page.getByRole('button', { name: 'stale record' }).click()
  await request
  await expect(page).toHaveURL(/fault=stale_record/)

  await page.getByRole('button', { name: /clear filters/i }).click()
  await expect(page).toHaveURL(/\/runs$/)
  await expect(page.getByText(`${RECORDED.runTotal} runs`)).toBeVisible()
})

test('searching is done by the server and counts the whole matching set', async ({ page }) => {
  await page.goto('/runs')
  const request = page.waitForRequest((call) => call.url().includes('q=refund'))
  await page.getByRole('searchbox', { name: /search runs/i }).fill('refund')
  await request
  await expect(page).toHaveURL(/q=refund/)
  await expect(page.locator('output')).toHaveText(/^\d+ runs? match(es)?$/)
  await expect(page.getByRole('row').nth(1)).toContainText('refund')
})

test('fault type is a server filter, including runs with none planted', async ({ page }) => {
  await page.goto('/runs')
  const request = page.waitForRequest((call) => call.url().includes('fault_type=none'))
  await page.getByRole('button', { name: /more filters/i }).click()
  await page.getByRole('button', { name: 'none planted' }).click()
  await request
  await expect(page).toHaveURL(/fault=none/)
  // "none planted" is about the injected fault, not about blame: an unplanted
  // run can still have been bisected. The check is that the server narrowed.
  const matched = await page.locator('output').textContent()
  expect(matched).toMatch(/^\d+ runs? match(es)?$/)
  expect(matched).not.toBe(`${RECORDED.runTotal} runs`)
})

test('sorting is requested from the server and announced on the header', async ({ page }) => {
  await page.goto('/runs')
  const steps = page.getByRole('columnheader', { name: /Steps/ })
  await expect(steps).not.toHaveAttribute('aria-sort', /ascending|descending/)

  await steps.getByRole('button').click()
  await expect(page).toHaveURL(/sort=n_steps/)
  await expect(steps).toHaveAttribute('aria-sort', 'ascending')

  await steps.getByRole('button').click()
  await expect(page).toHaveURL(/dir=desc/)
  await expect(steps).toHaveAttribute('aria-sort', 'descending')
})

test('rows are reachable by keyboard: arrows move, Enter opens', async ({ page }) => {
  await page.goto('/runs')
  const firstRow = page.getByRole('row').nth(1)
  await firstRow.focus()
  await expect(firstRow).toBeFocused()

  await page.keyboard.press('ArrowDown')
  const secondRow = page.getByRole('row').nth(2)
  await expect(secondRow).toBeFocused()
  await page.keyboard.press('ArrowUp')
  await expect(firstRow).toBeFocused()

  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/runs/${RECORDED.firstRunId}$`))
})

test('the list virtualizes: scrolling renders rows that were never in the DOM', async ({
  page,
}) => {
  await page.goto('/runs')
  const before = await page.getByRole('row').count()
  expect(before, 'far fewer rows than the corpus are rendered').toBeLessThan(RECORDED.runTotal)

  const lastId = RECORDED.lastRunId
  await expect(page.getByText(lastId, { exact: true })).toHaveCount(0)
  await page.getByRole('group', { name: /scrollable/ }).evaluate((node) => {
    node.scrollTop = node.scrollHeight
  })
  await expect(page.getByText(lastId, { exact: true })).toBeVisible()
})

test('a recording run is shown as recording, never as a failure', async ({ page }) => {
  await page.goto('/runs')
  await page.getByText('Recording', { exact: true }).first().click()
  await expect(page).toHaveURL(/status=recording/)
  await expect(page.getByText('Recording').first()).toBeVisible()
  await expect(page.locator('[data-outcome="fail"]')).toHaveCount(0)
  // No outcome, no cost attribution: an em dash, never a zero-effect blame badge.
  await expect(page.getByRole('row').nth(1).getByText('—').first()).toBeVisible()
})

test('filters that match nothing offer a way back', async ({ page }) => {
  await page.goto('/runs?q=zzzznothing')
  await expect(page.getByRole('heading', { name: 'No runs match these filters' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await expect(page.getByText(`${RECORDED.runTotal} runs`)).toBeVisible()
})

test('nothing recorded yet shows the command that would record something', async ({ page }) => {
  await page.unroute((url) => url.pathname === '/api/runs')
  await page.route(
    (url) => url.pathname === '/api/runs',
    (route) =>
      route.fulfill({
        json: {
          success: true,
          data: { status: 'not_available', reason: 'no recordings yet' },
          error: null,
          meta: { simulated: false, data_source: 'real' },
        },
      }),
  )
  await page.goto('/runs')
  await expect(page.getByText('bisect record --domain airline --tasks 0-19')).toBeVisible()
})

test('the command palette searches runs and opens one by keyboard alone', async ({ page }) => {
  await page.goto('/runs')
  // The shortcut is bound on mount; press it once the page is actually up.
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  await page.keyboard.press('ControlOrMeta+k')
  const palette = page.getByRole('dialog', { name: 'Command palette' })
  await expect(palette).toBeVisible()

  await page.keyboard.type('refund')
  // The search is debounced, so wait for a result that is actually a run.
  const firstHit = palette
    .getByRole('option')
    .filter({ hasText: /^(run|brief)-/ })
    .first()
  await expect(firstHit).toBeVisible()

  await page.keyboard.press('Enter')
  await expect(palette).toBeHidden()
  // Enter opens whichever run was selected, without the mouse ever being used.
  await expect(page).toHaveURL(/\/runs\/(run|brief)-[\w-]+$/)
})

test('390px collapses rows into cards rather than scrolling sideways', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/runs')
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Recorded runs' })).toBeVisible()

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow, 'no horizontal page overflow').toBeLessThanOrEqual(0)
})

test('390px puts the filters in a sheet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/runs')
  await page.getByRole('button', { name: 'Filters' }).click()
  const sheet = page.getByRole('dialog', { name: 'Filters' })
  await expect(sheet).toBeVisible()
  await sheet.getByText('✕ Fail').click()
  await expect(page).toHaveURL(/outcome=fail/)
})

for (const theme of ['dark', 'light'] as const) {
  test(`Runs has no serious or critical axe violations (${theme})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
      THEME_KEY,
      theme,
    ] as const)
    await page.goto('/runs')
    await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
    await page.waitForTimeout(1000)

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
