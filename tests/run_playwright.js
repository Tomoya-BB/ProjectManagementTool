delete process.env.FORCE_COLOR;
process.env.NO_COLOR = '1';

require(require.resolve('@playwright/test/cli'));
