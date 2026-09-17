import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

import { horizontalOverflow, mockP6eApi, applyTheme } from './p6e.fixtures'

const MOBILE = { width: 390, height: 844 } as const
const STREAM_FRAMES = 3

async function openLive(page: Page, theme: 'dark' | 'light' = 'dark'): Promise<void> {
  await applyTheme(page, theme)
  await page.goto('/live')
  await page.getByRole('heading', { level: 2, name: 'What the models are doing' }).waitFor()
}

test('the page receives and counts snapshots from the stream', async ({ page }) => {
  await mockP6eApi(page, { streamFrames: STREAM_FRAMES })
  await openLive(page)

  // Every frame is counted and its events reach the feed. The mocked body ends
  // after its last frame, so the chip then moves on from `live` by design.
  await expect(page.getByText(`${STREAM_FRAMES} updates`).first()).toBeVisible()
  await expect(page.getByText(/simulated: stream frame 2/)).toBeVisible()
  await expect(page.getByText(/^(live|reconnecting)$/).first()).toBeVisible()
})

test('the calls chart, gauge, ring, queue and feed all render', async ({ page }) => {
  await mockP6eApi(page)
  await openLive(page)

  await expect(page.getByText(/calls \/ min · sum of \d+ models?/)).toBeVisible()
  await expect(page.getByText(/traces share 0–\d+/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Call budget' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Headroom' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Jobs in flight' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent events' })).toBeVisible()
  // Two models, two traces.
  await expect(page.getByText(/peak .* · calls\/min/)).toHaveCount(2)
})

test('hovering one trace reads both of them at the same instant', async ({ page }) => {
  await mockP6eApi(page)
  await openLive(page)

  const cursor = page.locator('[data-slot="trace-cursor"]')
  await expect(cursor).toHaveCount(0)

  // Arrange — the middle of the first trace, which is the only trace hovered.
  const firstTrace = page.locator('svg[role="presentation"]').first()
  const box = await firstTrace.boundingBox()
  if (!box) throw new Error('the first trace has no box to hover')

  // Act
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)

  // Assert — the cursor lands on both traces, not just the hovered one.
  await expect(cursor).toHaveCount(2)

  await page.mouse.move(box.x + box.width / 2, box.y - 40)
  await expect(cursor).toHaveCount(0)
})

test('the event feed is a keyboard-reachable, politely announced log', async ({ page }) => {
  await mockP6eApi(page)
  await openLive(page)

  const feed = page.getByRole('group', { name: /Recent events, newest first/ })
  await feed.focus()
  await expect(feed).toBeFocused()
  await expect(feed.getByRole('list')).toHaveAttribute('aria-live', 'polite')
})

test('simulated traffic says so', async ({ page }) => {
  await mockP6eApi(page)
  await openLive(page)
  await expect(page.getByText(/Simulated traffic/)).toBeVisible()
})

test('a stream that never connects is reported, with a way to retry', async ({ page }) => {
  await mockP6eApi(page)
  await page.route('**/api/live/stream', (route) => route.abort('connectionrefused'))
  await openLive(page)

  // The snapshot still paints; only the stream is down.
  await expect(page.getByText(/reconnecting|offline/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry now' })).toBeVisible()
})

test('an unmeasured live endpoint is reported, never filled in with numbers', async ({ page }) => {
  await mockP6eApi(page, { unmeasured: true })
  await applyTheme(page, 'dark')
  await page.goto('/live')

  await expect(page.getByText(/live · not measured/i)).toBeVisible()
  await expect(page.getByText('no call ledger yet')).toBeVisible()
  await expect(page.getByText(/calls \/ min · sum of/)).toHaveCount(0)
})

test('the page does not scroll sideways at 390px', async ({ page }) => {
  await mockP6eApi(page)
  await page.setViewportSize(MOBILE)
  await openLive(page)
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)
})

for (const theme of ['dark', 'light'] as const) {
  test(`has no serious or critical axe violations in ${theme}`, async ({ page }) => {
    await mockP6eApi(page)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openLive(page, theme)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = results.violations.filter((violation) =>
      ['serious', 'critical'].includes(violation.impact ?? ''),
    )
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])
  })
}
