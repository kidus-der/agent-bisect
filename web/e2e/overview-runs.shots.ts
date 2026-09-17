/**
 * Round-1 design review shots for the Overview and Runs pages, in both themes
 * at 1440 and 390, plus a filtered Runs view and a mid-rewind frame.
 *
 * Like the e2e specs these replay the recorded fixture API, so a shot never
 * depends on a running `bisect serve` and never moves between runs.
 */
import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

import { mockApi } from './apiFixture'

const OUT_DIR = fileURLToPath(new URL('../../docs/screenshots/round2/', import.meta.url))
const THEME_KEY = 'bisect.theme'

const THEMES = ['dark', 'light'] as const
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '390', width: 390, height: 844 },
] as const

/**
 * The Overview scrolls, so it is captured whole. Runs is a fixed-height view
 * whose table scrolls inside itself — a full-page capture would stretch the
 * viewport, and the table sizes itself to the viewport, so it would grow to
 * fill a page that was only that tall because the table grew.
 */
const PAGES = [
  { name: 'overview', path: '/', fullPage: true },
  { name: 'runs', path: '/runs', fullPage: false },
  // A narrowed view: chips, a smaller count, and the rows that survived.
  {
    name: 'runs-filtered',
    path: '/runs?outcome=fail&domain=airline&fault=wrong_value',
    fullPage: false,
  },
] as const

const SETTLE_MS = 2200

async function prepare(page: Page, theme: string, path: string): Promise<void> {
  await mockApi(page)
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    THEME_KEY,
    theme,
  ] as const)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
}

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    for (const target of PAGES) {
      test(`${target.name} ${theme} ${viewport.name}`, async ({ page }) => {
        await page.setViewportSize(viewport)
        // Reduced motion pins the rewind on its final frame, so shots are stable.
        await page.emulateMedia({ reducedMotion: 'reduce' })
        await prepare(page, theme, target.path)
        await page.screenshot({
          path: `${OUT_DIR}${target.name}-${theme}-${viewport.name}.png`,
          fullPage: target.fullPage,
        })
      })
    }
  }

  test(`overview-rewind ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await mockApi(page)
    await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
      THEME_KEY,
      theme,
    ] as const)
    await page.goto('/')
    const loop = page.getByTestId('rewind-loop')
    await loop.scrollIntoViewIfNeeded()
    // Catch it mid-sweep: steps returning to tape, which is the moment worth seeing.
    await loop.locator('[data-phase="rewind"]').or(loop).first().waitFor()
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="rewind-loop"]')?.getAttribute('data-phase') ===
        'replay',
      undefined,
      { timeout: 25_000 },
    )
    await page.getByRole('button', { name: 'Pause' }).click()
    await page.screenshot({ path: `${OUT_DIR}overview-rewind-${theme}-1440.png` })
  })

  test(`runs-palette ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await prepare(page, theme, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('dialog', { name: 'Command palette' }).waitFor()
    await page.keyboard.type('refund')
    await page.getByRole('option').first().waitFor()
    await page.screenshot({ path: `${OUT_DIR}runs-palette-${theme}-1440.png` })
  })

  test(`runs-filters-sheet ${theme} 390`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await prepare(page, theme, '/runs')
    await page.getByRole('button', { name: 'Filters' }).click()
    await page.getByRole('dialog', { name: 'Filters' }).waitFor()
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${OUT_DIR}runs-filters-sheet-${theme}-390.png` })
  })
}
