import { test, expect } from '@playwright/test'
import { mockAPI } from './fixtures'

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockAPI(page)
  })

  test('loads dashboard by default', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/$|\/dashboard/)
    await expect(page.locator('nav')).toBeVisible()
  })

  test('navbar shows Ally logo/brand', async ({ page }) => {
    await page.goto('/')
    const nav = page.locator('nav')
    await expect(nav).toContainText('Ally')
  })

  test('can navigate to /builder', async ({ page }) => {
    await page.goto('/')
    const builderLink = page.locator('a[href*="builder"]')
    await builderLink.first().click()
    await expect(page).toHaveURL(/builder/)
  })

  test('can navigate to /logs', async ({ page }) => {
    await page.goto('/')
    const logsLink = page.locator('a[href*="logs"]')
    await logsLink.first().click()
    await expect(page).toHaveURL(/logs/)
  })

  test('active nav link is highlighted for dashboard', async ({ page }) => {
    await page.goto('/')
    // Look for the agents/dashboard nav link being active (indigo or underline class)
    const activeLink = page.locator('nav a.text-indigo-400, nav a[class*="indigo"], nav a[aria-current="page"]')
    await expect(activeLink.first()).toBeVisible()
  })

  test('active nav link is highlighted for builder', async ({ page }) => {
    await page.goto('/builder')
    const builderLink = page.locator('nav a[href*="builder"]')
    const className = await builderLink.first().getAttribute('class')
    expect(className).toMatch(/indigo|active|underline/)
  })

  test('active nav link is highlighted for logs', async ({ page }) => {
    await page.goto('/logs')
    const logsLink = page.locator('nav a[href*="logs"]')
    const className = await logsLink.first().getAttribute('class')
    expect(className).toMatch(/indigo|active|underline/)
  })
})
