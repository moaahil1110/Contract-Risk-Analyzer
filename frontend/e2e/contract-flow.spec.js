import { test, expect } from '@playwright/test'
import path from 'node:path'

const email = process.env.E2E_EMAIL
const password = process.env.E2E_PASSWORD
const pdfPath = process.env.E2E_PDF_PATH || path.resolve('../NDA.pdf')
const isCI = !!process.env.CI || process.env.VITE_CI_BYPASS_AUTH === 'true'

test.skip(!isCI && (!email || !password), 'Set E2E_EMAIL and E2E_PASSWORD to run authenticated E2E tests')

test('authenticated user can analyse, export, rerun, and delete a contract', async ({ page }) => {
  test.setTimeout(12 * 60 * 1000)

  if (isCI) {
    // In CI, auth is bypassed via VITE_CI_BYPASS_AUTH; navigate straight to dashboard
    await page.goto('/')
  } else {
    await page.goto('/login')
    await page.locator('input[type="email"]').fill(email)
    await page.locator('input[type="password"]').fill(password)
    await page.getByRole('button', { name: 'Sign In' }).click()
  }

  await expect(page.getByRole('heading', { name: 'Analyze a Contract' })).toBeVisible()
  await page.locator('select').first().selectOption('nda')
  await page.locator('input[type="file"]').setInputFiles(pdfPath)
  await page.getByRole('button', { name: 'Analyze Contract' }).click()

  await expect(page.locator('main').getByText(/Analysis queued|Extracting|Retrieving|Analysing|Analyzing/i).first()).toBeVisible({ timeout: 30_000 })
  await page.waitForURL(/\/results\//, { timeout: 10 * 60 * 1000 })

  await expect(page.getByText('Overall Score')).toBeVisible()
  await expect(page.getByText('Risk Breakdown')).toBeVisible()
  await expect(page.getByText('Full Clause Analysis')).toBeVisible()

  // Verify NDA contract type was detected and used
  await expect(page.getByText(/Type:\s*nda/i)).toBeVisible()
  // Verify visible RAG alignment metadata is present for at least one clause
  await expect(page.getByText(/RAG\s+(strong|partial|none)/i).first()).toBeVisible()

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export Report/i }).click()
  const report = await download
  expect(report.suggestedFilename()).toMatch(/risk-report-.*\.pdf$/)

  await page.getByRole('button', { name: /Back/i }).click()
  await expect(page.getByRole('heading', { name: 'Past Analyses' })).toBeVisible()

  const firstCompleteRow = page.locator('tbody tr').filter({ hasText: 'complete' }).first()
  await expect(firstCompleteRow).toBeVisible()
  await firstCompleteRow.getByTitle('Re-run Analysis').click()
  await page.getByRole('button', { name: 'Re-run', exact: true }).click()
  await expect(page.locator('tbody tr').filter({ hasText: /queued|extracting|retrieving|analysing|saving/i }).first()).toBeVisible({ timeout: 30_000 })

  const activeRow = page.locator('tbody tr').first()
  await activeRow.getByTitle('Delete').click()
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(page.getByText(/Cannot delete|Failed to delete|Running analyses cannot be deleted/i)).toBeVisible()
})
