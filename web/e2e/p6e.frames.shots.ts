import { fileURLToPath } from 'node:url'

import { test } from '@playwright/test'

import { applyTheme, mockP6eApi } from './p6e.fixtures'

const OUT_DIR = fileURLToPath(
  new URL(`../../docs/screenshots/${process.env.EVAL_ROUND ?? 'round4'}/`, import.meta.url),
)

const FRAME_COUNT = 10
/**
 * The gap between frames. A screenshot costs most of a frame on its own, so the
 * real cadence is roughly twice this; ten frames covers the staggered spring
 * from the first whisker to the last dot landing.
 */
const FRAME_GAP_MS = 60

/** Reduced motion is the opposite of what this sequence exists to show. */
test.use({ reducedMotion: 'no-preference' })

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
  // the first frame. The box is read once, after the scroll, and then reused —
  // nothing moves the page again.
  await panel.evaluate((element) => element.scrollIntoView({ block: 'center' }))
  const clip = (await panel.boundingBox()) ?? undefined

  for (let frame = 0; frame < FRAME_COUNT; frame += 1) {
    await page.screenshot({
      path: `${OUT_DIR}forest-entrance-${String(frame).padStart(2, '0')}.png`,
      clip,
    })
    await page.waitForTimeout(FRAME_GAP_MS)
  }
})
