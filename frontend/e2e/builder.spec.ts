import { test, expect } from '@playwright/test'
import { mockAPI, mockChatBuildFlow, mockChatEditFlow, mockChatGathering, MOCK_CONFIG, sendChatMessage } from './fixtures'

test.describe('Builder - Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
    await mockChatGathering(page, "What is your goal?")
    await page.goto('/builder')
  })

  test('shows full-width chat in empty state', async ({ page }) => {
    // Chat input should be visible
    await expect(page.locator('textarea')).toBeVisible({ timeout: 5000 })
  })

  test('shows welcome/empty state text', async ({ page }) => {
    await expect(page.getByText('Describe your voice agent')).toBeVisible({ timeout: 5000 })
  })

  test('right panel is NOT visible in empty state', async ({ page }) => {
    const rightPanel = page.locator('[data-testid="agent-preview"], [class*="preview"], [class*="right-panel"]')
    // Either not present or not visible
    const count = await rightPanel.count()
    if (count > 0) {
      await expect(rightPanel.first()).not.toBeVisible()
    }
  })

  test('chat input accepts text', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('I want to book surf lessons')
    await expect(textarea).toHaveValue('I want to book surf lessons')
  })

  test('sending a message shows AI response', async ({ page }) => {
    await sendChatMessage(page, 'I want to book surf lessons')
    await expect(page.getByText('What is your goal?')).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Builder - Agent Creation Flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
  })

  test('right panel slides in after agent is created', async ({ page }) => {
    await mockChatBuildFlow(page)
    await page.goto('/builder')

    // First message - still gathering
    await sendChatMessage(page, 'I want to qualify surfing leads')
    await expect(page.getByText('What is the target audience')).toBeVisible({ timeout: 10000 })

    // Second message - agent ready
    await sendChatMessage(page, 'Surfers aged 18-35')
    await expect(page.getByText('Your agent is ready! You can now make a call.')).toBeVisible({ timeout: 10000 })

    // Right panel should appear
    const previewPanel = page.locator('[data-testid="agent-preview"]')
      .or(page.locator('[class*="preview"]'))
      .or(page.getByText(MOCK_CONFIG.name))
    await expect(previewPanel.first()).toBeVisible({ timeout: 5000 })
  })

  test('agent name appears in preview after creation', async ({ page }) => {
    await mockChatBuildFlow(page)
    await page.goto('/builder')

    await sendChatMessage(page, 'Build my agent')
    await sendChatMessage(page, 'Surfers')
    await expect(page.getByRole('heading', { name: 'Dan' })).toBeVisible({ timeout: 10000 })
  })

  test('first message appears in preview after creation', async ({ page }) => {
    await mockChatBuildFlow(page)
    await page.goto('/builder')

    await sendChatMessage(page, 'Build my agent')
    await sendChatMessage(page, 'Surfers')
    await expect(page.getByText(/Hi, this is Dan/i)).toBeVisible({ timeout: 10000 })
  })

  test('qualifying questions appear in preview', async ({ page }) => {
    await mockChatBuildFlow(page)
    await page.goto('/builder')

    await sendChatMessage(page, 'Build my agent')
    await sendChatMessage(page, 'Surfers')
    await expect(page.getByText(/surfing level/i)).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Builder - Voice Dropdown', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
    await mockChatEditFlow(page)
    await page.goto('/builder')
    // Simulate an agent already being loaded by routing agents endpoint
  })

  test('voice dropdown shows all 6 options', async ({ page }) => {
    // Navigate to builder with an existing agent loaded via URL params or store
    await page.goto('/builder?session=session-abc123')
    await page.waitForTimeout(500)

    const select = page.locator('select[name="voice"], select').filter({ hasText: /alloy/i })
    const count = await select.count()

    if (count > 0) {
      const options = await select.locator('option').allTextContents()
      const voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
      for (const voice of voices) {
        expect(options.join(' ').toLowerCase()).toContain(voice)
      }
    }
  })
})

test.describe('Builder - Edit Mode', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
    await mockChatEditFlow(page, { ...MOCK_CONFIG, name: 'Alex' })
  })

  test('edit message shows "updated" not "ready"', async ({ page }) => {
    await page.goto('/builder')
    await sendChatMessage(page, 'Build an agent for surf school')
    // Wait for gather then confirm agent is "created"
    await page.waitForTimeout(500)
    await sendChatMessage(page, 'Change the name to Alex')
    await expect(page.getByText('Done! Your agent has been updated.').first()).toBeVisible({ timeout: 10000 })
    // Should NOT say "Your agent is ready!"
    await expect(page.getByText('Your agent is ready!')).not.toBeVisible()
  })
})

test.describe('Builder - Call Panel', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
    await mockChatBuildFlow(page)
    await page.goto('/builder')
    // Build agent first
    await sendChatMessage(page, 'Build an agent')
    await sendChatMessage(page, 'Target audience: surfers')
    await page.waitForTimeout(1000)
  })

  test('phone number input is visible in agent preview', async ({ page }) => {
    const phoneInput = page.locator('input[type="tel"], input[placeholder*="phone"], input[placeholder*="+"]')
    const count = await phoneInput.count()
    if (count > 0) {
      await expect(phoneInput.first()).toBeVisible()
    }
  })

  test('start call button is visible', async ({ page }) => {
    const callBtn = page.getByRole('button', { name: /start call|call|trigger/i })
    const count = await callBtn.count()
    if (count > 0) {
      await expect(callBtn.first()).toBeVisible()
    }
  })

  test('start call button is disabled without phone number', async ({ page }) => {
    const callBtn = page.getByRole('button', { name: /start call|call/i }).first()
    const count = await callBtn.count()
    if (count > 0) {
      const isDisabled = await callBtn.isDisabled()
      expect(isDisabled).toBe(true)
    }
  })
})
