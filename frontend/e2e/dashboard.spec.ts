import { test, expect } from '@playwright/test'
import { mockAPI, MOCK_AGENT } from './fixtures'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
  })

  test('shows agent cards when agents exist', async ({ page }) => {
    await page.goto('/')
    // Agent cards render as rounded divs with cursor-pointer; confirm at least one card appears
    await expect(page.locator('div.cursor-pointer').first()).toBeVisible({ timeout: 5000 })
  })

  test('agent card shows agent name', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(MOCK_AGENT.name, { exact: false })).toBeVisible({ timeout: 5000 })
  })

  test('agent card shows ACTIVE badge', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/active/i)).toBeVisible({ timeout: 5000 })
  })

  test('agent card shows voice', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/alloy/i)).toBeVisible({ timeout: 5000 })
  })

  test('clicking agent card navigates to builder', async ({ page }) => {
    await page.goto('/')
    const agentCard = page.locator('[data-testid="agent-card"], .agent-card, .cursor-pointer').first()
    await agentCard.waitFor({ timeout: 5000 })
    await agentCard.click()
    await expect(page).toHaveURL(/builder/)
  })

  test('"New Agent" button navigates to builder', async ({ page }) => {
    await page.goto('/')
    const newAgentBtn = page.getByRole('button', { name: /new agent/i })
      .or(page.getByRole('link', { name: /new agent/i }))
    await expect(newAgentBtn.first()).toBeVisible({ timeout: 5000 })
    await newAgentBtn.first().click()
    await expect(page).toHaveURL(/builder/)
  })

  test('shows empty state when no agents', async ({ page }) => {
    await page.route('**/api/agents', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.goto('/')
    await expect(page.getByText(/first|no agent|get started|build your/i)).toBeVisible({ timeout: 5000 })
  })
})
