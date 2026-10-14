// Renders each design in both themes and both languages: node render.mjs [hero how-it-works]
// (needs playwright; English files are name-theme.png, Portuguese name-theme.pt-BR.png).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '..');
const pages = process.argv.slice(2).length ? process.argv.slice(2) : ['hero', 'how-it-works'];

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1280, height: 800 } });
for (const name of pages) {
  for (const lang of ['en', 'pt-BR']) for (const theme of ['dark', 'light']) {
    await page.goto(`file://${here}/${name}.html?theme=${theme}&lang=${lang}`);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    const body = await page.$('body');
    const file = `${name}-${theme}${lang === 'en' ? '' : '.' + lang}.png`;
    await body.screenshot({ path: `${out}/${file}` });
    console.log(file);
  }
}
await browser.close();
