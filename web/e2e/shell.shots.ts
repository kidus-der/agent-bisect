/** `npm run screenshots -- shell`: shell, palette, states and gallery for design review. */
import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

import { mockApi } from './apiFixture'

// SHOTS_ROUND picks the review round the captures belong to.
const ROUND = process.env.SHOTS_ROUND ?? 'round3'
const OUT_DIR = fileURLToPath(new URL(`../../docs/screenshots/${ROUND}/shell/`, import.meta.url))
const THEMES = ['dark', 'light'] as const
const DESKTOP = { width: 1440, height: 900 }
const PHONE = { width: 390, height: 844 }
const SETTLE_MS = 2500

async function open(page: Page, theme: string, path: string, waitForTitle = true): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript((value) => window.localStorage.setItem('bisect.theme', value), theme)
  await page.goto(path)
  if (waitForTitle) await page.getByRole('heading', { level: 1 }).first().waitFor()
}

for (const theme of THEMES) {
  test(`palette with a run query ${theme}`, async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    await mockApi(page)
    await open(page, theme, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('combobox').fill('refund')
    await page.getByRole('option', { name: /Filter Runs by/ }).waitFor()
    await page.getByRole('option').first().waitFor()
    await page.waitForTimeout(800)
    await page.screenshot({ path: `${OUT_DIR}palette-query-${theme}-1440.png` })
  })

  test(`palette without a query ${theme}`, async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    await mockApi(page)
    await open(page, theme, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('dialog').waitFor()
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${OUT_DIR}palette-empty-${theme}-1440.png` })
  })

  test(`not found ${theme}`, async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    await mockApi(page)
    await open(page, theme, '/no-such-page', false)
    await page.getByText('Nothing is recorded at this address').waitFor()
    await page.screenshot({ path: `${OUT_DIR}not-found-${theme}-1440.png` })
  })

  test(`overview retrying then error ${theme}`, async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    // A predicate, not a glob: '**/api/**' would also abort the app's own /src/api modules.
    await page.route(
      (url) => url.pathname.startsWith('/api/'),
      (route) => route.abort('connectionrefused'),
    )
    await open(page, theme, '/', false)
    await page
      .getByText(/retrying…/)
      .first()
      .waitFor({ timeout: 15_000 })
    await page.screenshot({ path: `${OUT_DIR}retrying-overview-${theme}-1440.png` })
    await page.getByRole('alert').first().waitFor({ timeout: 30_000 })
    await page.screenshot({ path: `${OUT_DIR}error-overview-${theme}-1440.png` })
  })

  test(`overview ${theme}`, async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    await mockApi(page)
    await open(page, theme, '/')
    await page.waitForTimeout(SETTLE_MS)
    await page.screenshot({ path: `${OUT_DIR}overview-${theme}-1440.png` })
  })

  for (const viewport of [DESKTOP, PHONE]) {
    test(`gallery ${theme} ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await mockApi(page)
      await open(page, theme, '/gallery')
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
      await page.waitForTimeout(SETTLE_MS)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({
        path: `${OUT_DIR}gallery-${theme}-${viewport.width}.png`,
        fullPage: true,
      })
    })
  }
}

test('palette on a phone', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await mockApi(page)
  await open(page, 'dark', '/runs')
  await page.getByRole('button', { name: 'Open command palette' }).click()
  await page.getByRole('combobox').fill('refund')
  await page.getByRole('option', { name: /Filter Runs by/ }).waitFor()
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${OUT_DIR}palette-query-dark-390.png` })
})
