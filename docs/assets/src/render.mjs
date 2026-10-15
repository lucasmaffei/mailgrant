// Renders the README art: node render.mjs [hero how-it-works screens desktop]
// (needs playwright). English files are name.png, Portuguese name.pt-BR.png.
// The phone and desktop screenshots in shots/ come from demo/ (see demo/README.md).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '..');
const pages = process.argv.slice(2).length ? process.argv.slice(2) : ['hero', 'how-it-works', 'screens', 'desktop'];

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1280, height: 800 } });
for (const name of pages) {
  for (const lang of name === 'desktop' ? ['en'] : ['en', 'pt-BR']) {
    await page.goto(`file://${here}/${name}.html?lang=${lang}`);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    const file = `${name}${lang === 'en' ? '' : '.' + lang}.png`;
    await (await page.$('body')).screenshot({ path: `${out}/${file}` });
    console.log(file);
  }
}
await browser.close();
