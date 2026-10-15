import imaplib
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone(timedelta(hours=-3)))
def at(days, h, m): return (now - timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)
demo = {
 "contato@exemplo.com.br": [
   ("Mariana Duarte <mariana@clinicavida.com.br>", "Orçamento para o e-mail da clínica", at(0,9,41), False,
    "Oi! Tudo bem?\n\nSomos uma clínica com seis pessoas e hoje usamos o e-mail do provedor antigo, que vive caindo. Queria entender como funciona a migração das nossas caixas atuais e se as mensagens antigas vêm junto.\n\nTambém queria saber se dá para cada recepcionista ter o próprio endereço, e quanto ficaria por mês.\n\nObrigada!\nMariana"),
   ("Pedro Albuquerque <pedro@padariaalbuquerque.com.br>", "Re: Site novo da padaria", at(1,16,5), True,
    "Perfeito, pode seguir com a versão 2. Só troca a foto da vitrine pela que mandei ontem.\n\nAbraço,\nPedro"),
   ("Formulário do site <site@exemplo.com.br>", "Novo contato: link quebrado", at(3,18,20), True,
    "Um usuário relatou que um link curto da campanha de outubro está abrindo a página errada.\n\nPágina: https://exemplo.com.br/promo"),
 ],
 "financeiro@exemplo.com.br": [
   ("Cloudflare <billing@cloudflare.com>", "Sua fatura de outubro está disponível", at(0,8,12), False,
    "Fatura referente aos serviços de outubro. O pagamento será feito no cartão cadastrado."),
   ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", at(1,11,2), False,
    "Your payout is expected to arrive in your bank account on Oct 16."),
   ("Registro.br <cobranca@registro.br>", "Domínio exemplo.com.br renova em 30 dias", at(4,7,30), True,
    "A renovação automática está ativa. Confira os dados de pagamento antes do vencimento."),
 ],
 "lucas@exemplo.com.br": [
   ("Julia Matos <julia@agenciamatos.com.br>", "Reunião de quinta remarcada", at(0,7,55), False,
    "Lucas, a reunião de quinta passou para as 15h. Mesmo link de sempre."),
   ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", at(2,22,14), True,
    "All checks have passed on main."),
 ],
}
for user, msgs in demo.items():
    c = imaplib.IMAP4("127.0.0.1", 31143); c.login(user, "pass")
    for i, (frm, subj, when, seen, body) in enumerate(sorted(msgs, key=lambda m: m[2])):
        m = EmailMessage(); m["From"] = frm; m["To"] = user; m["Subject"] = subj
        m["Date"] = format_datetime(when); m["Message-ID"] = f"<demo{i}.{user}>"; m.set_content(body)
        c.append("INBOX", "(\\Seen)" if seen else "", imaplib.Time2Internaldate(when.timestamp()), m.as_bytes())
    c.logout()
print("seeded")
