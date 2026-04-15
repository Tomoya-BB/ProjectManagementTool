const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const workspaceDir = path.join(process.cwd(), 'tests', '.tmp', 'workspace');

async function expectDateScaleGantt(page) {
  const axisInfo = await page.evaluate(() => {
    const gd = document.querySelector('.plotly-graph-div');
    const range = gd?._fullLayout?.xaxis?.range || [];
    return {
      range,
      ticks: Array.from(document.querySelectorAll('.xtick text')).map((node) => node.textContent),
    };
  });

  const start = Date.parse(axisInfo.range[0]);
  const end = Date.parse(axisInfo.range[1]);
  expect(Number.isFinite(start)).toBeTruthy();
  expect(Number.isFinite(end)).toBeTruthy();
  expect(end - start).toBeGreaterThan(24 * 60 * 60 * 1000);
  expect(axisInfo.ticks.length).toBeGreaterThan(1);
}

async function bootstrapAndSelectProject(page) {
  await page.goto('/login');

  if (page.url().includes('/setup')) {
    await page.locator('input[name="username"]').fill('admin');
    await page.locator('input[name="password"]').fill('secret');
    await page.getByRole('button', { name: 'Create Admin' }).click();
  }

  if (page.url().includes('/login')) {
    await page.locator('input[name="username"]').fill('admin');
    await page.locator('input[name="password"]').fill('secret');
    await page.getByRole('button', { name: 'Login' }).click();
  }

  if (page.url().includes('/select')) {
    await page.locator('select[name="project"]').selectOption('project1');
    await page.getByRole('button', { name: 'Open' }).click();
  }

  await expect(page.getByRole('heading', { name: 'ダッシュボード' })).toBeVisible();
}

test('admin can manage members and tasks across the main screens', async ({ page }) => {
  await bootstrapAndSelectProject(page);

  await page.getByRole('link', { name: 'メンバー' }).click();
  await expect(page.getByRole('heading', { name: 'メンバー', exact: true })).toBeVisible();
  await page.locator('input[name="name"]').fill('Alice');
  await page.getByRole('button', { name: '追加' }).click();
  await expect(page.getByText('Alice', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'タスク' }).click();
  await expect(page.getByRole('heading', { name: 'タスク', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '新規タスク追加' }).click();

  await page.locator('#taskForm input[name="name"]').fill('Playwright task');
  await page.locator('#taskForm input[name="release_version"]').fill('v3.0');
  await page.locator('#taskForm input[name="start_date"]').fill('2026-04-20');
  await page.locator('#taskForm input[name="end_date"]').fill('2026-04-22');
  await page.locator('#taskForm textarea[name="remarks"]').fill('created in browser');
  await page.locator('#taskForm select[name="assignee_id"]').selectOption({ label: 'Alice' });
  await page.locator('#taskForm input[name="progress"]').fill('25');
  await page.locator('#taskFormSubmit').click();

  const row = page.locator('tr[data-task-row]').filter({ hasText: 'Playwright task' });
  await expect(row).toBeVisible();
  await expect(row).toContainText('25%');
  await expect(row).toContainText('Alice');

  await page.locator('#task-search').fill('Playwright');
  await expect(page.locator('#taskVisibleCount')).toHaveText('1');
  await expect(row).toBeVisible();

  await row.getByRole('button', { name: '編集' }).click();
  await expect(page.locator('#taskFormTitle')).toHaveText('タスク編集');
  await page.locator('#taskForm textarea[name="remarks"]').fill('updated in browser');
  await page.locator('#taskForm input[name="progress"]').fill('60');
  await page.locator('#taskFormSubmit').click();

  await expect(page.locator('tr[data-task-row]').filter({ hasText: 'Playwright task' })).toContainText('60%');
  await expect(page.locator('tr[data-task-row]').filter({ hasText: 'Playwright task' })).toContainText('updated in browser');

  await page.getByRole('link', { name: 'ダッシュボード' }).click();
  await expect(page.locator('#release-filter')).toContainText('v3.0');
  await expect(page.locator('.plot-frame .plotly-graph-div .main-svg').first()).toBeVisible();
  await expectDateScaleGantt(page);

  await page.getByRole('link', { name: 'ガントチャート' }).click();
  await expect(page.locator('#gantt-release')).toContainText('v3.0');
  await expect(page.locator('.plot-frame .plotly-graph-div .main-svg').first()).toBeVisible();
  await expectDateScaleGantt(page);
});

test('task form blocks invalid date ranges in the browser', async ({ page }) => {
  await bootstrapAndSelectProject(page);

  await page.getByRole('link', { name: 'タスク' }).click();
  await page.getByRole('button', { name: '新規タスク追加' }).click();
  await page.locator('#taskForm input[name="name"]').fill('Invalid browser task');
  await page.locator('#taskForm input[name="start_date"]').fill('2026-04-30');
  await page.locator('#taskForm input[name="end_date"]').fill('2026-04-01');
  await page.locator('#taskFormSubmit').click();

  await expect(page.locator('.toast-body')).toContainText('Start date must be before end date');
  await expect(page.locator('tr[data-task-row]').filter({ hasText: 'Invalid browser task' })).toHaveCount(0);
});

test('project creation and manifest upload work from the UI', async ({ page }) => {
  fs.mkdirSync(workspaceDir, { recursive: true });

  await bootstrapAndSelectProject(page);
  await page.getByRole('link', { name: '新規プロジェクト' }).click();
  await page.locator('input[name="project_name"]').fill('UIRoundTrip');
  await page.locator('input[name="save_path"]').fill(workspaceDir);
  await page.getByRole('button', { name: '作成' }).click();

  await expect(page.getByText('UIRoundTrip', { exact: true })).toBeVisible();

  const manifestPath = path.join(workspaceDir, 'UIRoundTrip', 'project.json');
  await expect.poll(() => fs.existsSync(manifestPath)).toBe(true);

  await page.getByRole('link', { name: 'プロジェクトを開く' }).click();
  await page.locator('input[type="file"][name="project_file"]').setInputFiles(manifestPath);
  await page.getByRole('button', { name: '開く' }).click();

  await expect(page.getByText("Project 'UIRoundTrip' opened.")).toBeVisible();
  await expect(page.getByText('UIRoundTrip', { exact: true })).toBeVisible();
});
