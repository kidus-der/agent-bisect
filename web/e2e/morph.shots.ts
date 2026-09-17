/**
 * Proof that the Runs row travels into the Run detail header rather than cutting
 * (signature moment §7.4).
 *
 * Sampled every 40ms from the click: the glide spring is largely done inside
 * ~300ms, so a sequence that starts sampling later only ever shows the settled
 * header and reads as a cut. Each frame also records the id chip's box, so the
 * travel is a measurement and not an impression — read morph-boxes.txt beside
 * the frames. Boxes come from the DOM rather than a locator: mid-flight the
 * element is transient, and a locator waits for a stability that never arrives.
 *
 * This one runs against a real `bisect serve --fixture`, not the recorded API
 * the other shots replay: that recording has no run-detail endpoint, so the
 * detail route renders its error state and there is nothing to morph into.
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { type Page, test } from '@playwright/test'

const OUT_DIR = fileURLToPath(new URL('../../docs/screenshots/round4/', import.meta.url))
const FRAME_COUNT = 10
const FRAME_MS = 40
const RUN_ID = 'run-0000'
const SETTLE_MS = 1200
/** The band the chip crosses: page header down through the first rows. */
const CLIP = { x: 0, y: 60, width: 760, height: 430 } as const

async function chipBox(page: Page, runId: string): Promise<string> {
  return page.evaluate((id) => {
    const matches = [...document.querySelectorAll('*')].filter(
      (element) => element.textContent?.trim() === id,
    )
    const match = matches[matches.length - 1]
    if (!match) return `absent (url ${location.pathname})`
    const { x, y, width, height } = match.getBoundingClientRect()
    return `<${match.tagName.toLowerCase()}> x ${Math.round(x)} y ${Math.round(y)} w ${Math.round(width)} h ${Math.round(height)}`
  }, runId)
}

test('the row morphs into the detail header', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/runs')
  const row = page.getByRole('row').filter({ hasText: RUN_ID }).first()
  await row.waitFor()
  await page.waitForTimeout(SETTLE_MS)
  await mkdir(OUT_DIR, { recursive: true })

  const boxes = [`click  ${await chipBox(page, RUN_ID)}`]
  await row.click()
  for (let frame = 0; frame < FRAME_COUNT; frame += 1) {
    const label = String(frame).padStart(2, '0')
    await page.screenshot({ path: `${OUT_DIR}morph-${label}.png`, clip: CLIP })
    boxes.push(`${label} +${frame * FRAME_MS}ms  ${await chipBox(page, RUN_ID)}`)
    await page.waitForTimeout(FRAME_MS)
  }
  await writeFile(`${OUT_DIR}morph-boxes.txt`, `${boxes.join('\n')}\n`, 'utf8')
})
