import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

import { BRIEF_RUN, EDGE_60_STEP, mockRunDetailApi } from './run-detail.fixtures'

const OUT_DIR = fileURLToPath(new URL('../../docs/screenshots/round4/', import.meta.url))

const THEMES = ['dark', 'light'] as const
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 1000 },
  { name: '390', width: 390, height: 844 },
] as const

const SETTLE_MS = 900

async function prepare(page: Page, theme: string, path: string): Promise<void> {
  await page.addInitScript((value) => window.localStorage.setItem('bisect.theme', value), theme)
  await mockRunDetailApi(page)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
}

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    test(`run-detail ${theme} ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      // Reduced motion pins entrances on their final frame, so shots are stable.
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await prepare(page, theme, `/runs/${BRIEF_RUN}`)
      await page.screenshot({
        path: `${OUT_DIR}run-detail-${theme}-${viewport.name}.png`,
        fullPage: true,
      })
    })
  }

  test(`run-detail 60-step ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await prepare(page, theme, `/runs/${EDGE_60_STEP}`)
    await page.screenshot({ path: `${OUT_DIR}run-detail-60step-${theme}-1440.png` })
  })

  test(`run-detail rerun-control ${theme} 1440`, async ({ page }) => {
    // The control arm is a different claim from the treated arm, so it is
    // captured as its own state.
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await prepare(page, theme, `/runs/${BRIEF_RUN}/reruns/${BRIEF_RUN}-c-0`)
    await page.screenshot({
      path: `${OUT_DIR}run-detail-rerun-control-${theme}-1440.png`,
      fullPage: true,
    })
  })

  test(`run-detail rerun ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await prepare(page, theme, `/runs/${BRIEF_RUN}/reruns/${BRIEF_RUN}-t7-0`)
    await page.screenshot({
      path: `${OUT_DIR}run-detail-rerun-${theme}-1440.png`,
      fullPage: true,
    })
  })
}

// Mid-rewind: motion stays on, so the tail is caught part-way through replaying.
test('run-detail rewind dark 1440', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await prepare(page, 'dark', `/runs/${BRIEF_RUN}`)
  await page.getByRole('button', { name: 'Rewind to k=7' }).click()
  await page.waitForTimeout(1900)
  await page.screenshot({ path: `${OUT_DIR}run-detail-rewind-dark-1440.png` })
})

test('run-detail rewind light 390', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await prepare(page, 'light', `/runs/${BRIEF_RUN}`)
  await page.getByRole('button', { name: 'Rewind to k=7' }).click()
  await page.waitForTimeout(1900)
  await page.screenshot({ path: `${OUT_DIR}run-detail-rewind-light-390.png` })
})

test('run-detail not bisected dark 1440', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await prepare(page, 'dark', '/runs/run-edge-zero-tested')
  await page.screenshot({ path: `${OUT_DIR}run-detail-not-bisected-dark-1440.png` })
})
