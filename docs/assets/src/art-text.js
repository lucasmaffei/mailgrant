// Words for the README art, per language. Pages read ?lang= and default to en.
const ART = {
  en: {
    tag: 'The email gateway for AI agents. <b>Each agent with its own mailboxes and permissions, and a webmail for you.</b>',
    sub: 'MCP · REST · installable web app · MIT',
    social: 'Self-hosted email for AI agents: one token per agent, its own mailboxes and scopes, MCP and REST, and a passkey webmail for you.',
    captions: [
      ['One inbox', 'Every mailbox by conversation, with what each agent already did.'],
      ['The whole conversation', 'Including what you sent, and HTML mail as it was designed.'],
      ['Real writing', 'Reply all, forward, attachments and drafts.'],
      ['Agents', 'Who read, sent or got denied, and when.'],
    ],
    how: {
      h: ['Who uses it', 'The gateway', 'Your mailboxes'],
      you: ['You, in the web app', 'passkey · whatever the config grants'],
      pts: [['Checks every call', 'against mailboxes and scopes.'], ['Hides the rest.', 'A mailbox outside a grant looks like it doesn’t exist.'], ['Keeps the passwords.', 'Nobody else sees them.'], ['Records and tells you:', 'audit log and phone push.']],
      boxes: [['contact@shop.com', 'hermes, support-bot, you'], ['billing@shop.com', 'finance-bot, you'], ['alex@shop.com', 'hermes, you'], ['ceo@shop.com', 'nobody']],
      denied: 'denied: finance-bot has no send',
    },
  },
  'pt-BR': {
    tag: 'O gateway de e-mail para agentes de IA. <b>Cada agente com as suas caixas e permissões, e um webmail para você.</b>',
    sub: 'MCP · REST · app web instalável · MIT',
    social: 'E-mail self-hosted para agentes de IA: um token por agente, com caixas e escopos próprios, MCP e REST, e um webmail com passkey para você.',
    captions: [
      ['Uma caixa de entrada', 'Todas as caixas, por conversa, com o que cada agente já fez.'],
      ['A conversa inteira', 'Inclusive o que você enviou, e e-mail HTML do jeito que foi desenhado.'],
      ['Escrever de verdade', 'Responder a todos, encaminhar, anexos e rascunhos.'],
      ['Agentes', 'Quem leu, enviou ou foi barrado, e quando.'],
    ],
    how: {
      h: ['Quem usa', 'O gateway', 'Suas caixas'],
      you: ['Você, no app web', 'passkey · tudo que o config der'],
      pts: [['Confere toda chamada', 'contra as caixas e os escopos.'], ['Esconde o resto.', 'Caixa fora da permissão parece não existir.'], ['Guarda as senhas.', 'Ninguém mais as vê.'], ['Registra e avisa:', 'auditoria e push no celular.']],
      boxes: [['contato@loja.com.br', 'hermes, support-bot, você'], ['financeiro@loja.com.br', 'finance-bot, você'], ['lucas@loja.com.br', 'hermes, você'], ['diretoria@loja.com.br', 'ninguém']],
      denied: 'negado: finance-bot não tem send',
    },
  },
  es: {
    tag: 'El gateway de correo para agentes de IA. <b>Cada agente con sus propios buzones y permisos, y un webmail para ti.</b>',
    sub: 'MCP · REST · app web instalable · MIT',
    social: 'Correo autoalojado para agentes de IA: un token por agente, con sus buzones y permisos, MCP y REST, y un webmail con passkey para ti.',
    captions: [
      ['Una sola bandeja', 'Todos los buzones por conversación, con lo que ya hizo cada agente.'],
      ['La conversación entera', 'Incluido lo que enviaste, y el correo HTML tal como se diseñó.'],
      ['Escribir de verdad', 'Responder a todos, reenviar, adjuntos y borradores.'],
      ['Agentes', 'Quién leyó, envió o fue bloqueado, y cuándo.'],
    ],
    how: {
      h: ['Quién lo usa', 'El gateway', 'Tus buzones'],
      you: ['Tú, en la app web', 'passkey · lo que permita la config'],
      pts: [['Revisa cada llamada', 'contra buzones y permisos.'], ['Oculta el resto.', 'Un buzón fuera del permiso parece no existir.'], ['Guarda las contraseñas.', 'Nadie más las ve.'], ['Registra y te avisa:', 'auditoría y push en el móvil.']],
      boxes: [['contacto@tienda.es', 'hermes, support-bot, tú'], ['facturacion@tienda.es', 'finance-bot, tú'], ['lucia@tienda.es', 'hermes, tú'], ['direccion@tienda.es', 'nadie']],
      denied: 'denegado: finance-bot no tiene send',
    },
  },
  fr: {
    tag: 'La passerelle e-mail pour les agents IA. <b>Chaque agent avec ses boîtes et ses droits, et un webmail pour vous.</b>',
    sub: 'MCP · REST · app web installable · MIT',
    social: 'L’e-mail auto-hébergé pour les agents IA : un jeton par agent, ses boîtes et ses droits, MCP et REST, et un webmail avec passkey pour vous.',
    captions: [
      ['Une seule boîte', 'Toutes les boîtes par conversation, avec ce que chaque agent a déjà fait.'],
      ['Toute la conversation', 'Y compris vos envois, et les e-mails HTML tels qu’ils ont été conçus.'],
      ['Écrire pour de vrai', 'Répondre à tous, transférer, pièces jointes et brouillons.'],
      ['Agents', 'Qui a lu, envoyé ou été bloqué, et quand.'],
    ],
    how: {
      h: ['Qui l’utilise', 'La passerelle', 'Vos boîtes'],
      you: ['Vous, dans l’app web', 'passkey · ce que la config autorise'],
      pts: [['Vérifie chaque appel', 'par rapport aux boîtes et aux droits.'], ['Cache le reste.', 'Une boîte hors autorisation semble ne pas exister.'], ['Garde les mots de passe.', 'Personne d’autre ne les voit.'], ['Trace et vous prévient :', 'journal d’audit et push sur le téléphone.']],
      boxes: [['contact@boutique.fr', 'hermes, support-bot, vous'], ['factures@boutique.fr', 'finance-bot, vous'], ['camille@boutique.fr', 'hermes, vous'], ['direction@boutique.fr', 'personne']],
      denied: 'refusé : finance-bot n’a pas send',
    },
  },
  'zh-CN': {
    tag: '为 AI 智能体打造的邮件网关。<b>每个智能体有自己的邮箱和权限，你还有一个网页邮箱。</b>',
    sub: 'MCP · REST · 可安装的网页应用 · MIT',
    social: '自托管的 AI 智能体邮件网关：每个智能体一个令牌，各自的邮箱和权限，支持 MCP 和 REST，还有一个用通行密钥登录的网页邮箱。',
    captions: [
      ['统一收件箱', '所有邮箱按会话排列，每个智能体做过什么一目了然。'],
      ['完整的会话', '包括你发出的邮件，HTML 邮件按原样显示。'],
      ['真正的写信', '回复全部、转发、附件和草稿。'],
      ['智能体', '谁读了、发了或被拒绝，以及时间。'],
    ],
    how: {
      h: ['使用者', '网关', '你的邮箱'],
      you: ['你，在网页应用里', '通行密钥 · 按配置授权'],
      pts: [['检查每一次调用', '是否符合邮箱和权限。'], ['隐藏其余的。', '未授权的邮箱看起来就像不存在。'], ['保管密码。', '其他人都看不到。'], ['记录并通知你：', '审计日志和手机推送。']],
      boxes: [['contact@shop.cn', 'hermes、support-bot、你'], ['billing@shop.cn', 'finance-bot、你'], ['lin@shop.cn', 'hermes、你'], ['ceo@shop.cn', '无人']],
      denied: '已拒绝：finance-bot 没有 send 权限',
    },
  },
};
const LANG = ART[new URLSearchParams(location.search).get('lang')] ? new URLSearchParams(location.search).get('lang') : 'en';
const A = ART[LANG];
document.documentElement.lang = LANG;
