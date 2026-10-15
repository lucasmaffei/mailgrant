// Renders the app icons into src/mailgrant/web/static/icons: node render-icons.mjs
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '../../../src/mailgrant/web/static/icons');
const jobs = [
  ['icon', 512, 'icon-512.png'], ['icon', 192, 'icon-192.png'], ['icon', 180, 'apple-touch-icon.png'],
  ['maskable', 512, 'maskable-512.png'], ['badge', 72, 'badge-72.png'],
];
const browser = await chromium.launch();
for (const [variant, size, file] of jobs) {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 }, deviceScaleFactor: size / 512 });
  await page.goto(`file://${here}/icon.html?v=${variant}`);
  await page.evaluate(() => document.fonts.ready);
  await (await page.$('#icon')).screenshot({ path: `${out}/${file}`, omitBackground: variant === 'badge' });
  console.log(file);
  await page.close();
}
await browser.close();
