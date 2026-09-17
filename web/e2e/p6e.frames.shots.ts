import { fileURLToPath } from 'node:url'

import { type Locator, type Page, test } from '@playwright/test'

import { applyTheme, mockP6eApi } from './p6e.fixtures'

const OUT_DIR = fileURLToPath(
  new URL(`../../docs/screenshots/${process.env.EVAL_ROUND ?? 'round5'}/`, import.meta.url),
)

const FRAME_COUNT = 10
/**
 * The gap between frames. A screenshot costs most of a frame on its own, so the
 * real cadence is roughly twice this; ten frames covers a staggered spring from
 * the first mark moving to the last one landing.
 */
const FRAME_GAP_MS = 60

/** Reduced motion is the opposite of what these sequences exist to show. */
test.use({ reducedMotion: 'no-preference' })

/**
 * Frames of one panel, starting the instant `trigger` returns, with the elapsed
 * time written into each file name. The timings are the evidence: "the entrance
 * is perceptible" is a claim about milliseconds, and a sequence of stills that
 * does not say when each was taken cannot support it.
 */
async function captureFrames(
  page: Page,
  panel: Locator,
  name: string,
  trigger: () => Promise<void>,
): Promise<void> {
  await trigger()
  const started = Date.now()
  const clip = (await panel.boundingBox()) ?? undefined
  for (let frame = 0; frame < FRAME_COUNT; frame += 1) {
    const elapsed = String(Date.now() - started).padStart(4, '0')
    await page.screenshot({
      path: `${OUT_DIR}${name}-${String(frame).padStart(2, '0')}-${elapsed}ms.png`,
      clip,
    })
    await page.waitForTimeout(FRAME_GAP_MS)
  }
}

test('gate-history forest entrance', async ({ page }) => {
  // Short on purpose: at 900 the panel is already on screen when the page loads,
  // so its once-only entrance has run before the first frame can be taken.
  await page.setViewportSize({ width: 1440, height: 560 })
  await mockP6eApi(page)
  await applyTheme(page, 'dark')

  await page.goto('/pr-checks')
  await page.getByRole('heading', { name: 'PR checks' }).first().waitFor()
  // Let the rest of the page settle first, so the only thing moving in the
  // sequence is the forest.
  await page.waitForTimeout(1200)

  const panel = page.locator('section', {
    has: page.getByRole('heading', { name: 'What the gate has caught' }),
  })
  await panel.waitFor()

  // The plot enters when it is 40% in view, so it has to start outside it.
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(400)
  const startsBelowTheFold = await panel.evaluate(
    (element) => element.getBoundingClientRect().top > window.innerHeight,
  )
  if (!startsBelowTheFold) throw new Error('the forest is already on screen; it cannot enter')

  // A raw scroll rather than scrollIntoViewIfNeeded: the latter waits for the
  // element to settle, which is long enough for the entrance to be over before
  // the first frame.
  await captureFrames(page, panel, 'forest-entrance', () =>
    panel.evaluate((element) => element.scrollIntoView({ block: 'center' })),
  )
})

test('benchmark method bars entrance', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mockP6eApi(page)
  await applyTheme(page, 'dark')

  // Arriving from another route, which is how anyone reaches this page: the bars
  // wait out the page's own transition before they start drawing.
  await page.goto('/live')
  await page.getByRole('heading', { name: 'What the models are doing' }).waitFor()
  await page.waitForTimeout(800)

  const panel = page.locator('section', {
    has: page.getByRole('heading', { name: 'Which method blames the right step' }),
  })

  await captureFrames(page, panel, 'benchmark-entrance', async () => {
    await page.getByRole('link', { name: 'Benchmark' }).first().click()
    await panel.waitFor()
  })
})
