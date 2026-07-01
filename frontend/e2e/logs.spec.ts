import { test, expect } from '@playwright/test'
import { mockAPI, MOCK_CALL_LOG } from './fixtures'

test.describe('Call Logs', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
    await page.goto('/logs')
  })

  test('shows call log table', async ({ page }) => {
    await expect(page.locator('table, [role="table"], [data-testid="logs-table"]').first()).toBeVisible({ timeout: 5000 })
  })

  test('shows agent name in table', async ({ page }) => {
    await expect(page.getByText(MOCK_CALL_LOG.agent_name)).toBeVisible({ timeout: 5000 })
  })

  test('shows phone number in table', async ({ page }) => {
    await expect(page.getByText(MOCK_CALL_LOG.phone_number)).toBeVisible({ timeout: 5000 })
  })

  test('shows sentiment in transcript drawer', async ({ page }) => {
    // Sentiment is shown in the drawer, not the table column — click a row first
    const row = page.locator('tr').filter({ hasText: MOCK_CALL_LOG.agent_name })
    await row.first().click()
    await expect(page.getByText('Positive')).toBeVisible({ timeout: 5000 })
  })

  test('clicking a row opens transcript drawer', async ({ page }) => {
    const row = page.locator('tr, [role="row"]').filter({ hasText: MOCK_CALL_LOG.agent_name })
    await row.first().click()
    // Transcript text should appear
    await expect(page.getByText(/transcript/i, { exact: false })).toBeVisible({ timeout: 5000 })
  })

  test('transcript drawer shows conversation turns', async ({ page }) => {
    const row = page.locator('tr, [role="row"]').filter({ hasText: MOCK_CALL_LOG.agent_name })
    await row.first().click()
    await expect(page.getByText(/Hi, this is Dan/i)).toBeVisible({ timeout: 5000 })
  })

  test('transcript drawer shows duration metric', async ({ page }) => {
    const row = page.locator('tr').filter({ hasText: MOCK_CALL_LOG.agent_name })
    await row.first().click()
    // 154s = "2:34" via formatDuration — visible in the drawer metrics sidebar
    await expect(page.getByRole('paragraph').filter({ hasText: /^2:34$/ })).toBeVisible({ timeout: 5000 })
  })

  test('shows empty state when no logs', async ({ page }) => {
    await page.route('**/api/calls/logs', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.reload()
    await expect(page.getByText(/no calls|no logs|empty|yet/i)).toBeVisible({ timeout: 5000 })
  })

  test('search filters by agent name', async ({ page }) => {
    const searchInput = page.locator('input[type="search"], input[placeholder*="search"], input[placeholder*="Search"]')
    const count = await searchInput.count()
    if (count > 0) {
      await searchInput.first().fill('Dan')
      await expect(page.getByText('Dan')).toBeVisible()
      await searchInput.first().fill('ZZZNOMATCH')
      await expect(page.getByText('Dan')).not.toBeVisible()
    }
  })
})
