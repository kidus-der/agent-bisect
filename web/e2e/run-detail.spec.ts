import AxeBuilder from '@axe-core/playwright'
import { type Page, expect, test } from '@playwright/test'

import { BRIEF_RUN, EDGE_60_STEP, mockRunDetailApi } from './run-detail.fixtures'

const THEME_KEY = 'bisect.theme'

function tapeCells(page: Page, state: string) {
  return page.getByTestId('tape-lane').locator(`[data-state="${state}"]`)
}

async function openRun(page: Page, runId: string, theme: 'dark' | 'light' = 'dark'): Promise<void> {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    THEME_KEY,
    theme,
  ] as const)
  await page.goto(`/runs/${runId}`)
  await page.getByRole('slider', { name: 'Step playhead' }).waitFor()
}

test.beforeEach(async ({ page }) => {
  await mockRunDetailApi(page)
})

test('the header states the run, its outcome and the step blame landed on', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  await expect(page.getByRole('heading', { level: 1, name: BRIEF_RUN })).toBeVisible()
  await expect(page.getByText('refund_after_cancellation')).toBeVisible()
  await expect(page.getByText('Fail', { exact: true })).toBeVisible()
  await expect(page.getByTestId('run-simulated-flag')).toBeVisible()
  // Blame never appears without its number and interval.
  await expect(page.getByText('[+0.47, +0.96]').first()).toBeVisible()
  await expect(page.getByText('planted fault · wrong_value at step 7')).toBeVisible()
})

test('the playhead opens on the decisive step and moves by keyboard', async ({ page }) => {
  await openRun(page, BRIEF_RUN)
  const slider = page.getByRole('slider', { name: 'Step playhead' })

  await expect(slider).toHaveAttribute('aria-valuenow', '7')
  await expect(slider).toHaveAttribute('aria-valuetext', 'step 7 of 12, tool book_reservation')

  await slider.focus()
  await page.keyboard.press('ArrowRight')
  await expect(slider).toHaveAttribute('aria-valuenow', '8')
  await page.keyboard.press('Home')
  await expect(slider).toHaveAttribute('aria-valuenow', '1')
  await page.keyboard.press('End')
  await expect(slider).toHaveAttribute('aria-valuenow', '12')
  await page.keyboard.press('PageDown')
  await expect(slider).toHaveAttribute('aria-valuenow', '7')
})

test('dragging the playhead scrubs the tape and the inspector follows', async ({ page }) => {
  await openRun(page, BRIEF_RUN)
  const slider = page.getByRole('slider', { name: 'Step playhead' })
  const box = await slider.boundingBox()
  expect(box).not.toBeNull()
  if (!box) return

  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.95, box.y + box.height / 2, { steps: 12 })
  await page.mouse.up()

  await expect(slider).toHaveAttribute('aria-valuenow', '12')
  await expect(page.getByRole('heading', { name: 'Step 12' })).toBeVisible()
})

test('rewinding to step 7 bands the tape, tags the intervention and replays the tail', async ({
  page,
}) => {
  await openRun(page, BRIEF_RUN)

  await page.getByRole('button', { name: 'Rewind to k=7' }).click()

  await expect(page.getByText('read from tape · 0 calls')).toBeVisible()
  await expect(page.getByText('tool result replaced')).toBeVisible()
  await expect(page.getByText('NM1VX1', { exact: true })).toBeVisible()
  await expect(page.getByText('ZFA04Y', { exact: true })).toBeVisible()
  await expect(page.getByText(/re-run live × \d+/)).toBeVisible()
  // The tail settles on the outcome the recorded treated re-runs actually had.
  // The tape is a graphic, so its cells are asserted by state, not by role.
  await expect(tapeCells(page, 'passed')).toHaveCount(1, { timeout: 15_000 })
  await expect(tapeCells(page, 'tape')).toHaveCount(6)
  await expect(page.getByRole('button', { name: 'Recording' })).toBeVisible()
})

test('the forest plot draws every estimate with its interval, against delta', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  await expect(page.getByText('δ 0.10', { exact: true })).toBeVisible()
  const blamedRow = page.getByRole('button', {
    name: 'Step 7, effect +0.88, 95% interval +0.47 to +0.96, the earliest step clearing the threshold',
  })
  await expect(blamedRow).toBeVisible()
  await expect(blamedRow).toHaveAttribute('aria-pressed', 'true')

  // Selecting a row moves the playhead with it.
  await page.getByRole('button', { name: /^Step 8, effect/ }).click()
  await expect(page.getByRole('slider', { name: 'Step playhead' })).toHaveAttribute(
    'aria-valuenow',
    '8',
  )
})

test('the forest plot repeats its numbers as a table for screen readers', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  const table = page.getByRole('table', {
    name: 'Per-step causal effect with its 95% confidence interval',
  })
  await expect(table.getByRole('row')).toHaveCount(13)
})

test('a dot in the matrix opens the re-run it stands for', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  await page.getByRole('link', { name: /Re-run 1 of 8, treated step 7/ }).click()

  await expect(page.getByRole('heading', { level: 1, name: /-t7-0$/ })).toBeVisible()
  await expect(page.getByText(/forked at k=7/)).toBeVisible()
  await expect(page.getByText('fork · intervention applied here')).toBeVisible()
  await expect(page.getByText('read from tape · 0 calls').first()).toBeVisible()
})

test('the judge panel compares both protocols with the measured effect', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  await expect(page.getByText(/judge rank 1 = step 7/)).toBeVisible()
  await page.getByText('Step by step', { exact: true }).click()
  await expect(page.getByRole('button', { name: /judge score 0.689/ })).toBeVisible()
})

test('the DB-state diff counts what step 7 changed', async ({ page }) => {
  await openRun(page, BRIEF_RUN)

  await page.getByRole('tab', { name: 'DB state' }).click()
  await expect(page.getByText('~1 changed')).toBeVisible()
  await expect(page.getByText('membership')).toBeVisible()
})

test('a run with no tested steps explains itself and names the command', async ({ page }) => {
  await openRun(page, 'run-edge-zero-tested')

  await expect(page.getByRole('heading', { name: 'This run has not been bisected' })).toBeVisible()
  await expect(page.getByText('bisect blame run-edge-zero-tested --top 3 --n 8')).toBeVisible()
})

test('a run where nothing clears delta says so honestly', async ({ page }) => {
  await openRun(page, 'run-edge-no-clear')

  await expect(page.getByText(/no step.s 95% interval had a lower bound above δ/)).toBeVisible()
})

test('an unknown run id is a designed 404, not a crash', async ({ page }) => {
  await page.goto('/runs/definitely-not-a-run')

  await expect(page.getByRole('heading', { name: 'No run definitely-not-a-run' })).toBeVisible()
})

test('the API being down shows the error state and retry recovers', async ({ page }) => {
  await page.route(
    (url) => url.pathname === `/api/runs/${BRIEF_RUN}`,
    (route) => route.abort('connectionrefused'),
  )
  await page.goto(`/runs/${BRIEF_RUN}`)

  await expect(page.getByRole('alert')).toContainText('Cannot reach the Bisect server')
  await page.unrouteAll()
  await mockRunDetailApi(page)
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { level: 1, name: BRIEF_RUN })).toBeVisible()
})

for (const [label, width, height] of [
  ['1440', 1440, 900],
  ['390', 390, 844],
] as const) {
  test(`a 60-step run stays inside the viewport at ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await openRun(page, EDGE_60_STEP)

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBe(0)
    await expect(page.getByTestId('timeline-minimap')).toBeVisible()
    await expect(page.getByRole('slider', { name: 'Step playhead' })).toHaveAttribute(
      'aria-valuemax',
      '60',
    )
  })
}

for (const theme of ['dark', 'light'] as const) {
  test(`no serious or critical accessibility violations in ${theme}`, async ({ page }) => {
    await openRun(page, BRIEF_RUN, theme)
    await page.waitForTimeout(500)

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    )
    expect(
      blocking.flatMap((violation) =>
        violation.nodes.map((node) => `${violation.id} @ ${node.target.join(' ')}`),
      ),
    ).toEqual([])
  })
}

test('reduced motion turns the rewind into a static before and after', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openRun(page, BRIEF_RUN)

  await page.getByRole('button', { name: 'Rewind to k=7' }).click()

  // No replay sequence to wait through: the settled state is there immediately.
  await expect(tapeCells(page, 'passed')).toHaveCount(1, { timeout: 2000 })
  await expect(tapeCells(page, 'tape')).toHaveCount(6)
})
