import { chromium, devices } from 'playwright';
import fs from 'node:fs';

const invite = fs.readFileSync('invite.txt', 'utf8').trim();
const out = process.argv[2] || 'shots';
fs.mkdirSync(out, { recursive: true });
const problems = [];
const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['iPhone 14 Pro'], deviceScaleFactor: 3, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error' || /Content Security Policy/i.test(m.text())) problems.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
const cdp = await ctx.newCDPSession(page);
await cdp.send('WebAuthn.enable');
await cdp.send('WebAuthn.addVirtualAuthenticator', { options: { protocol: 'ctap2', transport: 'internal', hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true } });
const step = async (name, fn) => { try { await fn(); console.log('ok   ', name); } catch (e) { console.log('FAIL ', name, '-', e.message.split('\n')[0]); problems.push(`${name}: ${e.message.split('\n')[0]}`); } };

await step('abre convite', async () => { await page.goto(invite); await page.getByRole('button', { name: 'Criar passkey' }).waitFor(); });
await page.screenshot({ path: `${out}/01-convite.png` });
await step('cria passkey e entra', async () => { await page.getByRole('button', { name: 'Criar passkey' }).click(); await page.locator('.row').first().waitFor({ timeout: 15000 }); });
await step('estrela na conversa', async () => { await page.locator('.row-wrap', { hasText: 'Orçamento' }).locator('.star').click(); await page.locator('.star.on').waitFor(); });
await page.waitForTimeout(3600);
await page.screenshot({ path: `${out}/02-entrada.png` });
await step('marca do hermes na lista', async () => { await page.getByText('hermes leu').first().waitFor(); });
await step('filtra por caixa', async () => { await page.locator('.chip', { hasText: 'financeiro@exemplo' }).click(); await page.waitForFunction(() => document.querySelectorAll('.row').length === 3); });
await step('volta para todas', async () => { await page.locator('.chip', { hasText: 'Todas' }).click(); await page.waitForFunction(() => document.querySelectorAll('.row').length === 8); });
await step('abre a conversa', async () => { await page.locator('.row', { hasText: 'Orçamento' }).click(); await page.getByRole('heading', { name: 'Orçamento para o e-mail da clínica' }).waitFor(); await page.locator('.tmsg').nth(2).waitFor(); });
// Fold the first message so the shot shows the answer from Sent and the attachment.
await page.locator('.tmsg-head').first().click();
await page.waitForTimeout(3600);
await page.screenshot({ path: `${out}/03-mensagem.png` });
await step('linha do hermes na mensagem', async () => { await page.locator('.agent-line', { hasText: 'hermes leu' }).waitFor(); });
await step('responder a todos com anexo', async () => {
  await page.locator('.detail-foot [aria-label="Responder a todos"]').click(); await page.locator('#cc').waitFor();
  await page.locator('#files').setInputFiles({ name: 'proposta-lumahost.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n'.repeat(4000)) });
  await page.locator('.att', { hasText: 'proposta-lumahost.pdf' }).waitFor();
});
await page.locator('#body').evaluate((el) => { el.value = 'Combinado! Segue a proposta para as seis caixas. A migração das mensagens antigas entra sem custo.' + el.value; el.dispatchEvent(new Event('input', { bubbles: true })); el.blur(); });
await page.waitForTimeout(3600);
await page.screenshot({ path: `${out}/04-resposta.png` });
await step('envia', async () => { await page.getByRole('button', { name: 'Enviar' }).click(); await page.getByText('Enviado.').waitFor(); });
await step('agentes', async () => { await page.goto(invite.replace(/#.*/, '#/agents')); await page.locator('.event').first().waitFor(); });
await page.waitForTimeout(3600);
await page.screenshot({ path: `${out}/05-agentes.png` });
await step('ajustes', async () => { await page.goto(invite.replace(/#.*/, '#/settings')); await page.getByText('Passkeys').waitFor(); await page.locator('.switch').first().waitFor(); });
await page.waitForTimeout(3600);
await page.screenshot({ path: `${out}/06-ajustes.png`, fullPage: false });
await step('preferência salva', async () => { const sw = page.locator('.switch').nth(1); await sw.click(); await page.waitForFunction(() => document.querySelectorAll('.switch')[1].getAttribute('aria-checked') === 'false'); });
await step('sair', async () => { await page.getByRole('button', { name: 'Sair deste aparelho' }).click(); await page.getByRole('button', { name: 'Entrar com passkey' }).waitFor(); });
await page.screenshot({ path: `${out}/00-entrar.png` });
await step('entra de novo com a passkey', async () => { await page.getByRole('button', { name: 'Entrar com passkey' }).click(); await page.locator('.tabs').waitFor({ timeout: 15000 }); await page.getByRole('heading', { name: 'Ajustes' }).waitFor(); });

// desktop
const desk = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });
const dp = await desk.newPage();
dp.on('pageerror', (e) => problems.push(`desk pageerror: ${e.message}`));
await desk.addCookies((await ctx.cookies()).map((c) => ({ ...c })));
await step('desktop: lista e mensagem lado a lado', async () => {
  await dp.goto(invite.replace(/#.*/, '#/m/contato/3'));
  await dp.getByRole('heading', { name: 'Orçamento para o e-mail da clínica' }).waitFor();
  await dp.locator('.row').first().waitFor();
});
await dp.waitForTimeout(800);
await dp.screenshot({ path: `${out}/07-desktop.png` });
console.log(problems.length ? `\nPROBLEMAS:\n${problems.join('\n')}` : '\nsem erros de console nem CSP');
await browser.close();
