// Renders the README art: node render.mjs [hero how-it-works screens desktop social]
// (needs playwright). English files are name.png, other languages name.<lang>.png.
// The phone and desktop screenshots in shots/<lang>/ come from demo/ (see demo/README.md).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '..');
const LANGS = ['en', 'pt-BR', 'es', 'fr', 'zh-CN'];
const pages = process.argv.slice(2).length ? process.argv.slice(2) : ['hero', 'how-it-works', 'screens', 'desktop', 'social'];

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1280, height: 800 } });
for (const name of pages) {
  // The social preview is uploaded by hand in the repo settings; English only.
  for (const lang of name === 'social' ? ['en'] : LANGS) {
    await page.goto(`file://${here}/${name}.html?lang=${lang}`);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    const file = `${name}${lang === 'en' ? '' : '.' + lang}.png`;
    await (await page.$('body')).screenshot({ path: `${out}/${file}`, scale: name === 'social' ? 'css' : 'device' });
    console.log(file);
  }
}
await browser.close();
