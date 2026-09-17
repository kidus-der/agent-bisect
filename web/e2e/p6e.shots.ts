import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

import { mockP6eApi, applyTheme } from './p6e.fixtures'

const OUT_DIR = fileURLToPath(
  new URL(`../../docs/screenshots/${process.env.EVAL_ROUND ?? 'round2'}/`, import.meta.url),
)

const THEMES = ['dark', 'light'] as const
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '390', width: 390, height: 844 },
] as const

const PAGES = [
  { name: 'benchmark', path: '/benchmark', ready: 'Which method blames the right step' },
  { name: 'live', path: '/live', ready: 'What the models are doing' },
  { name: 'pr-checks', path: '/pr-checks', ready: 'PR checks' },
  { name: 'pr-check-detail', path: '/pr-checks/pr-check-00', ready: 'Where the blame rule lands' },
] as const

/** Long enough for the vendored charts to finish their entrance. */
const CHART_SETTLE_MS = 1600
/** Entrances are IntersectionObserver-driven, so the page is walked, not jumped. */
const SCROLL_STEP_MS = 320
/** Enough SSE frames for the Live page to look like it is running. */
const STREAM_FRAMES = 4

/**
 * Walks the page one viewport at a time. Entrances fire on
 * IntersectionObserver, and an instant jump to the bottom never intersects the
 * middle of a long page — which left whole sections at opacity 0 in the shot.
 */
async function walkPage(page: Page): Promise<void> {
  const steps = await page.evaluate(
    () => Math.ceil(document.body.scrollHeight / window.innerHeight) + 1,
  )
  for (let step = 0; step < steps; step += 1) {
    await page.evaluate((index) => window.scrollTo(0, index * window.innerHeight), step)
    await page.waitForTimeout(SCROLL_STEP_MS)
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(CHART_SETTLE_MS)
}

async function capture(page: Page, target: (typeof PAGES)[number]): Promise<void> {
  await page.goto(target.path)
  await page.getByRole('heading', { name: target.ready }).first().waitFor()
  await page.waitForTimeout(CHART_SETTLE_MS)
  await walkPage(page)
}

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    for (const target of PAGES) {
      test(`${target.name} ${theme} ${viewport.name}`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height })
        await mockP6eApi(page, { streamFrames: STREAM_FRAMES })
        await applyTheme(page, theme)
        await capture(page, target)
        await page.screenshot({
          path: `${OUT_DIR}${target.name}-${theme}-${viewport.name}.png`,
          fullPage: true,
        })
      })
    }
  }
}
