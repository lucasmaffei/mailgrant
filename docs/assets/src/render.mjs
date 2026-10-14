// Renders each design in both themes: node render.mjs (needs playwright).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '..');
const pages = process.argv.slice(2).length ? process.argv.slice(2) : ['hero', 'how-it-works'];

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1280, height: 800 } });
for (const name of pages) {
  for (const theme of ['dark', 'light']) {
    await page.goto(`file://${here}/${name}.html?theme=${theme}`);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    const body = await page.$('body');
    await body.screenshot({ path: `${out}/${name}-${theme}.png` });
    console.log(`${name}-${theme}.png`);
  }
}
await browser.close();
