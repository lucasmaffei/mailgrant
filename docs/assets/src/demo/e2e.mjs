// Real screenshots of the web app for the README, in one language:
// node e2e.mjs <lang> <invite file> <out dir>   (run.sh calls it for each language)
// Signs in with a virtual WebAuthn authenticator, walks the screens and fails
// on any console or CSP error.
import { chromium, devices } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const [lang = 'en', inviteFile = 'invite.txt', out = 'shots'] = process.argv.slice(2);
const here = path.dirname(fileURLToPath(import.meta.url));
const dict = lang === 'en' ? {} : JSON.parse(fs.readFileSync(path.resolve(here, `../../../../src/mailgrant/web/static/i18n/${lang}.json`), 'utf8'));
// The text a button shows in this language (keys may carry a "context|" prefix).
const L = (key) => { const v = dict[key]; return typeof v === 'string' ? v : key.replace(/^[a-z]+\|/, ''); };
const { CONTENT } = JSON.parse(fs.readFileSync(path.resolve(here, 'content.json'), 'utf8'));
const C = CONTENT[lang];
const clinic = [...C.mail.contact].sort((a, b) => b[2] - a[2] || a[3] - b[3])[2][1];
const locale = { en: 'en-US', 'pt-BR': 'pt-BR', es: 'es-ES', fr: 'fr-FR', 'zh-CN': 'zh-CN' }[lang];

const invite = fs.readFileSync(inviteFile, 'utf8').trim();
const base = invite.replace(/#.*/, '');
fs.mkdirSync(out, { recursive: true });
const problems = [];
const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['iPhone 14 Pro'], deviceScaleFactor: 3, locale, timezoneId: 'America/Sao_Paulo' });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning' || /Content Security Policy/i.test(m.text())) problems.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
const cdp = await ctx.newCDPSession(page);
await cdp.send('WebAuthn.enable');
await cdp.send('WebAuthn.addVirtualAuthenticator', { options: { protocol: 'ctap2', transport: 'internal', hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true } });
const step = async (name, fn) => { try { await fn(); console.log('ok   ', name); } catch (e) { console.log('FAIL ', name, '-', e.message.split('\n')[0]); problems.push(`${name}: ${e.message.split('\n')[0]}`); } };
const shot = async (name) => { await page.waitForTimeout(3600); await page.screenshot({ path: `${out}/${name}.png` }); };

await step('sign in', async () => {
  await page.goto(invite);
  await page.getByRole('button', { name: L('Create passkey') }).click();
  await page.locator('.row').first().waitFor({ timeout: 15000 });
});
await step('star the conversation', async () => { await page.locator('.row-wrap', { hasText: clinic }).locator('.star').click(); await page.locator('.star.on').waitFor(); });
await shot('inbox');
await step('open the conversation', async () => {
  await page.locator('.row', { hasText: clinic }).click();
  await page.getByRole('heading', { name: clinic }).waitFor();
  await page.locator('.tmsg').nth(2).waitFor();
});
// Fold the first message so the shot shows the answer from Sent and the attachment.
await page.locator('.tmsg-head').first().click();
await shot('conversation');
await step('reply all with an attachment', async () => {
  await page.locator('.detail-foot a[href*="replyall"]').click();
  await page.locator('#cc').waitFor();
  await page.locator('#files').setInputFiles({ name: C.attachment, mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n'.repeat(4000)) });
  await page.locator('.att', { hasText: C.attachment }).waitFor();
});
await page.locator('#body').evaluate((el, text) => { el.value = text + el.value; el.dispatchEvent(new Event('input', { bubbles: true })); el.blur(); }, C.compose);
await shot('compose');
await step('send', async () => { await page.getByRole('button', { name: L('Send'), exact: true }).click(); await page.getByText(L('Sent.')).first().waitFor(); });
await step('agents', async () => { await page.goto(base + '#/agents'); await page.locator('.event').first().waitFor(); });
await shot('agents');
await step('settings', async () => { await page.goto(base + '#/settings'); await page.locator('.settings-nav').waitFor(); });
await shot('settings');

const desk = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale, timezoneId: 'America/Sao_Paulo' });
await desk.addCookies(await ctx.cookies());
const dp = await desk.newPage();
dp.on('pageerror', (e) => problems.push(`desktop pageerror: ${e.message}`));
await step('desktop: list and conversation side by side', async () => {
  await dp.goto(base + '#/m/contact/3');
  await dp.getByRole('heading', { name: clinic }).waitFor();
  await dp.locator('.row').first().waitFor();
});
await dp.waitForTimeout(1200);
await dp.screenshot({ path: `${out}/desktop.png` });
await browser.close();
console.log(problems.length ? `\nPROBLEMS (${lang}):\n${problems.join('\n')}` : `\n${lang}: no console or CSP errors`);
if (problems.length) process.exit(1);
