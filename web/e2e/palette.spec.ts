import { expect, test } from '@playwright/test'

import { mockApi } from './apiFixture'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('on a phone the selected run previews under the list, since there is no side pane', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/runs')
  await page.getByRole('button', { name: 'Open command palette' }).click()
  await page.getByRole('combobox').fill('refund')
  const preview = page.getByTestId('palette-preview-compact')
  await expect(preview).toBeVisible()
  await expect(preview).toContainText(/\d+ steps/)
  const dialog = page.getByRole('dialog', { name: 'Command palette' })
  const box = await dialog.boundingBox()
  expect(box && box.y + box.height).toBeLessThanOrEqual(844)
})

test('on a desktop the preview lives in the side pane and the compact one is hidden', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/runs')
  // The shortcut listener only exists once the shell has mounted.
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('combobox').fill('refund')
  await expect(page.getByRole('option').first()).toBeVisible()
  await expect(page.getByTestId('palette-preview-compact')).toBeHidden()
})

test('the footer says what Enter does', async ({ page }) => {
  await page.goto('/runs')
  // The shortcut listener only exists once the shell has mounted.
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.keyboard.press('ControlOrMeta+k')
  await expect(page.getByRole('dialog', { name: 'Command palette' })).toContainText('open')
})
