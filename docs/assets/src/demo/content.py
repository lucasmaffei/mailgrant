"""Demo mail for the README screenshots, one set per web app language.

Every language gets mail that reads naturally in it: local names, local
domains, the same story (a clinic asks for a quote, a bakery approves a site,
a form reports a broken link, invoices, a moved meeting). Mailbox *names* stay
the same everywhere (contact, billing, me) so the agent script and the
screenshot script don't care which language is on screen.
"""

# Each message: (from, subject, days ago, hour, minute, seen, body)
CONTENT = {
    "en": {
        "boxes": {"contact": "contact@example.com", "billing": "billing@example.com", "me": "alex@example.com"},
        "mail": {
            "contact": [
                ("Maria Lopez <maria@brightclinic.com>", "Quote for the clinic's email", 0, 9, 41, False,
                 "Hi! Hope you're well.\n\nWe're a clinic of six people and our current provider's email keeps going down. I'd like to understand how moving our mailboxes works and whether the old messages come along.\n\nCould each receptionist have their own address, and what would it cost per month?\n\nThanks!\nMaria"),
                ("Peter Walsh <peter@walshbakery.com>", "Re: New bakery website", 1, 16, 5, True,
                 "Perfect, go ahead with version 2. Just swap the shop window photo for the one I sent yesterday.\n\nCheers,\nPeter"),
                ("Website form <site@example.com>", "New contact: broken link", 3, 18, 20, True,
                 "A visitor reported that a short link from the October campaign opens the wrong page.\n\nPage: https://example.com/promo"),
            ],
            "billing": [
                ("Cloudflare <billing@cloudflare.com>", "Your October invoice is available", 0, 8, 12, False,
                 "Invoice for October's services. It will be charged to the card on file."),
                ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", 1, 11, 2, False,
                 "Your payout is expected to arrive in your bank account on Oct 16."),
                ("Namecheap <billing@namecheap.com>", "example.com renews in 30 days", 4, 7, 30, True,
                 "Auto-renew is on. Check your payment details before the due date."),
            ],
            "me": [
                ("Julia Bennett <julia@bennettstudio.com>", "Thursday's meeting moved", 0, 7, 55, False,
                 "Alex, Thursday's meeting is now at 3 pm. Same link as always."),
                ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", 2, 22, 14, True,
                 "All checks have passed on main."),
            ],
        },
        "answer": "Hi Maria!\n\nMoving the old messages is included, and each receptionist can have their own address. Six mailboxes fit the Team plan.\n\nShall I send you the proposal?",
        "follow": ("Yes, please! I've copied reception. Here's our current provider's quote to compare.\n\nMaria", "Reception <reception@brightclinic.com>", "current-quote.pdf"),
        "agent_reply": "Sounds good, Peter! Version 2 with the new shop window photo goes live this afternoon.",
        "compose": "Great! Here's the proposal for the six mailboxes. Moving the old messages is free.",
        "attachment": "proposal.pdf",
    },
    "pt-BR": {
        "boxes": {"contact": "contato@exemplo.com.br", "billing": "financeiro@exemplo.com.br", "me": "lucas@exemplo.com.br"},
        "mail": {
            "contact": [
                ("Mariana Duarte <mariana@clinicavida.com.br>", "Orçamento para o e-mail da clínica", 0, 9, 41, False,
                 "Oi! Tudo bem?\n\nSomos uma clínica com seis pessoas e hoje usamos o e-mail do provedor antigo, que vive caindo. Queria entender como funciona a migração das nossas caixas atuais e se as mensagens antigas vêm junto.\n\nTambém queria saber se dá para cada recepcionista ter o próprio endereço, e quanto ficaria por mês.\n\nObrigada!\nMariana"),
                ("Pedro Albuquerque <pedro@padariaalbuquerque.com.br>", "Re: Site novo da padaria", 1, 16, 5, True,
                 "Perfeito, pode seguir com a versão 2. Só troca a foto da vitrine pela que mandei ontem.\n\nAbraço,\nPedro"),
                ("Formulário do site <site@exemplo.com.br>", "Novo contato: link quebrado", 3, 18, 20, True,
                 "Um usuário relatou que um link curto da campanha de outubro está abrindo a página errada.\n\nPágina: https://exemplo.com.br/promo"),
            ],
            "billing": [
                ("Cloudflare <billing@cloudflare.com>", "Sua fatura de outubro está disponível", 0, 8, 12, False,
                 "Fatura referente aos serviços de outubro. O pagamento será feito no cartão cadastrado."),
                ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", 1, 11, 2, False,
                 "Your payout is expected to arrive in your bank account on Oct 16."),
                ("Registro.br <cobranca@registro.br>", "Domínio exemplo.com.br renova em 30 dias", 4, 7, 30, True,
                 "A renovação automática está ativa. Confira os dados de pagamento antes do vencimento."),
            ],
            "me": [
                ("Julia Matos <julia@agenciamatos.com.br>", "Reunião de quinta remarcada", 0, 7, 55, False,
                 "Lucas, a reunião de quinta passou para as 15h. Mesmo link de sempre."),
                ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", 2, 22, 14, True,
                 "All checks have passed on main."),
            ],
        },
        "answer": "Oi, Mariana!\n\nA migração das mensagens antigas é inclusa, e cada recepcionista pode ter o próprio endereço. Para seis caixas fica no plano Equipe.\n\nQuer que eu mande a proposta?",
        "follow": ("Quero sim! Coloquei a recepção em cópia. Segue o orçamento do provedor atual para comparar.\n\nMariana", "Recepção <recepcao@clinicavida.com.br>", "orcamento-atual.pdf"),
        "agent_reply": "Combinado, Pedro! A versão 2 com a foto nova da vitrine sobe hoje à tarde.",
        "compose": "Combinado! Segue a proposta para as seis caixas. A migração das mensagens antigas entra sem custo.",
        "attachment": "proposta.pdf",
    },
    "es": {
        "boxes": {"contact": "contacto@ejemplo.es", "billing": "facturacion@ejemplo.es", "me": "lucia@ejemplo.es"},
        "mail": {
            "contact": [
                ("María Fernández <maria@clinicasol.es>", "Presupuesto para el correo de la clínica", 0, 9, 41, False,
                 "¡Hola! ¿Qué tal?\n\nSomos una clínica de seis personas y el correo de nuestro proveedor actual se cae cada dos por tres. Quería entender cómo funciona la migración de nuestros buzones y si los mensajes antiguos vienen también.\n\n¿Cada recepcionista podría tener su propia dirección? ¿Cuánto costaría al mes?\n\n¡Gracias!\nMaría"),
                ("Pedro Ruiz <pedro@panaderiaruiz.es>", "Re: Web nueva de la panadería", 1, 16, 5, True,
                 "Perfecto, adelante con la versión 2. Solo cambia la foto del escaparate por la que te mandé ayer.\n\nUn abrazo,\nPedro"),
                ("Formulario de la web <web@ejemplo.es>", "Nuevo contacto: enlace roto", 3, 18, 20, True,
                 "Un visitante avisa de que un enlace corto de la campaña de octubre abre la página equivocada.\n\nPágina: https://ejemplo.es/promo"),
            ],
            "billing": [
                ("Cloudflare <billing@cloudflare.com>", "Tu factura de octubre ya está disponible", 0, 8, 12, False,
                 "Factura de los servicios de octubre. Se cargará en la tarjeta registrada."),
                ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", 1, 11, 2, False,
                 "Your payout is expected to arrive in your bank account on Oct 16."),
                ("Dinahosting <facturas@dinahosting.com>", "El dominio ejemplo.es se renueva en 30 días", 4, 7, 30, True,
                 "La renovación automática está activa. Revisa tus datos de pago antes del vencimiento."),
            ],
            "me": [
                ("Julia Morales <julia@estudiomorales.es>", "Cambio de hora de la reunión del jueves", 0, 7, 55, False,
                 "Lucía, la reunión del jueves pasa a las 15:00. El enlace de siempre."),
                ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", 2, 22, 14, True,
                 "All checks have passed on main."),
            ],
        },
        "answer": "¡Hola, María!\n\nLa migración de los mensajes antiguos está incluida, y cada recepcionista puede tener su propia dirección. Seis buzones entran en el plan Equipo.\n\n¿Te mando la propuesta?",
        "follow": ("¡Sí, por favor! He puesto a recepción en copia. Te adjunto el presupuesto del proveedor actual para comparar.\n\nMaría", "Recepción <recepcion@clinicasol.es>", "presupuesto-actual.pdf"),
        "agent_reply": "¡Perfecto, Pedro! La versión 2 con la foto nueva del escaparate se publica esta tarde.",
        "compose": "¡Genial! Te envío la propuesta para los seis buzones. La migración de los mensajes antiguos no tiene coste.",
        "attachment": "propuesta.pdf",
    },
    "fr": {
        "boxes": {"contact": "contact@exemple.fr", "billing": "factures@exemple.fr", "me": "camille@exemple.fr"},
        "mail": {
            "contact": [
                ("Marie Dubois <marie@cliniquesoleil.fr>", "Devis pour la messagerie de la clinique", 0, 9, 41, False,
                 "Bonjour,\n\nNous sommes une clinique de six personnes et la messagerie de notre fournisseur actuel tombe sans arrêt. J’aimerais comprendre comment se passe la migration de nos boîtes et si les anciens messages suivent.\n\nChaque secrétaire pourrait-elle avoir sa propre adresse ? Et combien cela coûterait par mois ?\n\nMerci !\nMarie"),
                ("Pierre Martin <pierre@boulangeriemartin.fr>", "Re: Nouveau site de la boulangerie", 1, 16, 5, True,
                 "Parfait, partez sur la version 2. Changez juste la photo de la vitrine par celle envoyée hier.\n\nBien à vous,\nPierre"),
                ("Formulaire du site <site@exemple.fr>", "Nouveau contact : lien cassé", 3, 18, 20, True,
                 "Un visiteur signale qu’un lien court de la campagne d’octobre ouvre la mauvaise page.\n\nPage : https://exemple.fr/promo"),
            ],
            "billing": [
                ("Cloudflare <billing@cloudflare.com>", "Votre facture d’octobre est disponible", 0, 8, 12, False,
                 "Facture des services d’octobre. Elle sera prélevée sur la carte enregistrée."),
                ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", 1, 11, 2, False,
                 "Your payout is expected to arrive in your bank account on Oct 16."),
                ("Gandi <facturation@gandi.net>", "Le domaine exemple.fr est renouvelé dans 30 jours", 4, 7, 30, True,
                 "Le renouvellement automatique est activé. Vérifiez vos informations de paiement avant l’échéance."),
            ],
            "me": [
                ("Julie Moreau <julie@studiomoreau.fr>", "Réunion de jeudi déplacée", 0, 7, 55, False,
                 "Camille, la réunion de jeudi passe à 15 h. Même lien que d’habitude."),
                ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", 2, 22, 14, True,
                 "All checks have passed on main."),
            ],
        },
        "answer": "Bonjour Marie,\n\nLa migration des anciens messages est incluse, et chaque secrétaire peut avoir sa propre adresse. Six boîtes rentrent dans l’offre Équipe.\n\nVoulez-vous que je vous envoie la proposition ?",
        "follow": ("Oui, volontiers ! J’ai mis l’accueil en copie. Voici le devis de notre fournisseur actuel pour comparer.\n\nMarie", "Accueil <accueil@cliniquesoleil.fr>", "devis-actuel.pdf"),
        "agent_reply": "Entendu, Pierre ! La version 2 avec la nouvelle photo de la vitrine est en ligne cet après-midi.",
        "compose": "Parfait ! Voici la proposition pour les six boîtes. La migration des anciens messages est offerte.",
        "attachment": "proposition.pdf",
    },
    "zh-CN": {
        "boxes": {"contact": "contact@example.cn", "billing": "billing@example.cn", "me": "lin@example.cn"},
        "mail": {
            "contact": [
                ("王丽 <wangli@kangning-clinic.cn>", "诊所企业邮箱报价咨询", 0, 9, 41, False,
                 "您好！\n\n我们是一家六个人的诊所，现在用的邮箱服务商经常出故障。想了解一下现有邮箱怎么迁移过来，以前的邮件能不能一起迁移。\n\n另外，每位前台能不能有自己的邮箱地址？每个月大概多少钱？\n\n谢谢！\n王丽"),
                ("陈伟 <chenwei@chenji-bakery.cn>", "回复：面包店新网站", 1, 16, 5, True,
                 "很好，就用第 2 版吧。只是把橱窗那张照片换成我昨天发的那张。\n\n陈伟"),
                ("网站表单 <site@example.cn>", "新留言：链接失效", 3, 18, 20, True,
                 "有访客反馈，十月活动的一个短链接打开的是错误页面。\n\n页面：https://example.cn/promo"),
            ],
            "billing": [
                ("Cloudflare <billing@cloudflare.com>", "您的十月账单已生成", 0, 8, 12, False,
                 "十月服务账单，将从已绑定的银行卡扣款。"),
                ("Stripe <support@stripe.com>", "Payout of $214.50 is on its way", 1, 11, 2, False,
                 "Your payout is expected to arrive in your bank account on Oct 16."),
                ("阿里云 <billing@aliyun.com>", "域名 example.cn 将在 30 天后续费", 4, 7, 30, True,
                 "已开启自动续费，请在到期前确认付款信息。"),
            ],
            "me": [
                ("周婷 <zhouting@zhou-studio.cn>", "周四的会议改时间了", 0, 7, 55, False,
                 "林总，周四的会议改到下午 3 点，还是原来的链接。"),
                ("GitHub <noreply@github.com>", "[mailgrant] CI passed on main", 2, 22, 14, True,
                 "All checks have passed on main."),
            ],
        },
        "answer": "王女士您好！\n\n以前的邮件可以免费迁移，每位前台也都可以有自己的地址。六个邮箱正好适合团队版。\n\n需要我把方案发给您吗？",
        "follow": ("好的，麻烦发一下！我抄送了前台。附件是现在服务商的报价，方便对比。\n\n王丽", "前台 <qiantai@kangning-clinic.cn>", "现有报价.pdf"),
        "agent_reply": "好的，陈先生！换了新橱窗照片的第 2 版今天下午上线。",
        "compose": "好的！附上六个邮箱的方案，以前邮件的迁移不收费。",
        "attachment": "方案.pdf",
    },
}
