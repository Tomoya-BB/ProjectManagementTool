const { defineConfig } = require('@playwright/test');
const path = require('path');

const port = 5011;

module.exports = defineConfig({
  testDir: path.join(__dirname, 'tests', 'e2e'),
  fullyParallel: false,
  reporter: 'list',
  timeout: 30_000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'bash tests/run_e2e_server.sh',
    url: `http://127.0.0.1:${port}/login`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
