import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

const OUT_DIR = fileURLToPath(new URL('../../docs/screenshots/round0/', import.meta.url))

const THEMES = ['dark', 'light'] as const
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '390', width: 390, height: 844 },
] as const
const PAGES = [
  { name: 'gallery', path: '/gallery', fullPage: true, offline: false },
  { name: 'shell-runs-empty', path: '/runs', fullPage: false, offline: false },
  { name: 'shell-overview-error', path: '/', fullPage: false, offline: true },
] as const

const CHART_SETTLE_MS = 2500

const META = { simulated: true, data_source: 'fixture' }
const META_PAYLOAD = {
  ...META,
  package_version: '0.0.0-shots',
  tau2_commit: 'shots',
  agent_model: 'shots-agent',
  user_model: 'shots-user',
  generated_at: '2026-01-01T00:00:00Z',
}

/** Shots never depend on a running `bisect serve`; `offline` captures the error state instead. */
async function mockMeta(page: Page, offline: boolean): Promise<void> {
  await page.route('**/api/meta', (route) =>
    offline
      ? route.abort('connectionrefused')
      : route.fulfill({ json: { success: true, data: META_PAYLOAD, error: null, meta: META } }),
  )
}

async function prepare(page: Page, theme: string, path: string): Promise<void> {
  await page.addInitScript((value) => window.localStorage.setItem('bisect.theme', value), theme)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
}

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    for (const target of PAGES) {
      test(`${target.name} ${theme} ${viewport.name}`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height })
        // Reduced motion pins the rewind illustration on its final frame, so shots are stable.
        await page.emulateMedia({ reducedMotion: 'reduce' })
        await mockMeta(page, target.offline)
        await prepare(page, theme, target.path)
        if (target.fullPage) {
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
          await page.waitForTimeout(CHART_SETTLE_MS)
          await page.evaluate(() => window.scrollTo(0, 0))
        }
        await page.screenshot({
          path: `${OUT_DIR}${target.name}-${theme}-${viewport.name}.png`,
          fullPage: target.fullPage,
        })
      })
    }
  }

  test(`palette ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await mockMeta(page, false)
    await prepare(page, theme, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('dialog').waitFor()
    await page.screenshot({ path: `${OUT_DIR}palette-${theme}-1440.png` })
  })
}
