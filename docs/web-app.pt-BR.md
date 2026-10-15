# O app web

[English](web-app.md)

O mailgrant também pode servir um app web pequeno para **você**: uma caixa de
entrada com todas as suas caixas, o que cada agente leu e enviou, e
notificações push no celular. Ele vai para a tela de início como um app, e você
entra com passkey (Face ID, Touch ID, Windows Hello, chave de segurança): não
existe senha.

Ele fica **desligado até você ligar**. Sem a seção `web:` no config, o
mailgrant continua sendo um gateway MCP/REST sem estado: nenhuma rota web,
nenhum banco, nenhuma dependência extra carregada.

![O app web no celular](assets/screens.pt-BR.png)

## O que tem

| Tela | O que faz |
|---|---|
| Entrada | Todas as caixas que você pode ver, das mais novas para as mais antigas, com filtro por caixa e busca. Cada mensagem mostra qual agente já leu ou respondeu. |
| Mensagem | O corpo em texto limpo (o HTML é convertido, nunca interpretado), anexos para baixar, os agentes que mexeram nela. A resposta entra na mesma conversa e fica em Enviados. |
| Agentes | A auditoria como linha do tempo: leituras, envios, idas para a lixeira e cada recusa, com filtro por envios ou por barrados. |
| Ajustes | Ligar notificações, escolher quais caixas notificam, receber push quando um agente enviar e-mail, gerenciar passkeys, ver o acesso de cada agente. |

No computador vira três colunas: caixas, lista e mensagem.

![O app web no computador](assets/desktop.png)

## Como ligar

Acrescente uma seção `web:` ao config:

```yaml
web:
  origin: https://mail.exemplo.com.br      # a URL pública que você abre
  data_dir: /data                          # SQLite: passkeys, aparelhos, histórico
  user:
    name: lucas
    mailboxes: ["*"]                       # como um agente: nomes, endereços ou "*"
    scopes: [read, mark, delete, send]
  # poll_seconds: 60                       # de quanto em quanto tempo procura e-mail novo
  # session_days: 30
  # push_contact: mailto:voce@exemplo.com.br  # contato para os serviços de push; padrão: origin
```

- `origin` precisa ser `https://` (passkey e push só funcionam em origem
  segura; `http://localhost` é aceito para teste). Pedidos vindos de qualquer
  outra origem são recusados.
- `user` recebe permissão exatamente como um agente. Dê menos escopos a você
  mesmo se quiser um celular só de leitura.
- `data_dir` precisa ser persistente (um volume do Docker). Não guarda e-mail.

Reinicie e confira:

```bash
mailgrant check
# web app: on at https://mail.exemplo.com.br/app for lucas [delete, mark, read, send]  all mailboxes; data in /data
```

## A primeira passkey

Ninguém entra antes de algum aparelho ter uma passkey. Há dois jeitos de criar
a primeira: um código de configuração no ambiente, ou um link de convite.

### Com código de configuração (sem terminal)

Defina um código no ambiente, com 12 caracteres ou mais (no Coolify, uma
variável de ambiente nova; no Compose, no `.env`):

```bash
MAILGRANT_SETUP_CODE=$(openssl rand -hex 12)
```

Reinicie e abra o app: no lugar de "Entrar com passkey" ele pede o **Código de
configuração**. Digite, confirme com Face ID / Touch ID, e você entrou.

O código **só vale enquanto não existe passkey**. Assim que a primeira é
criada, a tela volta ao normal e o código passa a ser recusado: um `.env`
antigo não serve para cadastrar aparelho depois. Pode apagar a variável em
seguida. `web.setup_code` no config faz o mesmo, e tem prioridade sobre a
variável.

### Com link de convite

No servidor:

```bash
mailgrant invite            # vale 30 minutos, uma vez (--minutes muda)
# https://mail.exemplo.com.br/app/#/invite/Lweu52CZ…
```

No Docker: `docker compose exec mailgrant mailgrant invite`. No Coolify, use a
aba **Terminal** da aplicação.

Abra o link no celular ou computador que vai guardar a passkey, dê um nome ao
aparelho e confirme com Face ID / Touch ID. Pronto, você entrou.

**Outros aparelhos:** no app, **Ajustes → Adicionar outro aparelho** gera um
convite novo para abrir no outro aparelho. A última passkey não pode ser
removida, para você não se trancar para fora por engano; se perder todos os
aparelhos, rode `mailgrant invite` no servidor de novo.

## Instalar e ligar as notificações

**iPhone / iPad (iOS 16.4 ou mais novo)**: as notificações só funcionam com o
app na Tela de Início.

1. Abra a URL no Safari e toque em **Compartilhar → Adicionar à Tela de Início**.
2. Abra o mailgrant pelo ícone novo (não pelo Safari).
3. **Ajustes → Ativar notificações**, e permita quando o iOS perguntar.

**Android / Chrome, Edge e Firefox no computador**: abra a URL, entre,
**Ajustes → Ativar notificações**. Chrome e Edge também oferecem **Instalar app**.

Depois escolha quais caixas notificam. **Testar** manda um push de teste para
todos os aparelhos com notificação ligada.

### Como o e-mail novo é detectado

A cada `poll_seconds` (60 por padrão) o mailgrant pergunta o `STATUS` de cada
caixa (um comando leve, sem baixar nada) e só manda push das mensagens que
chegaram desde a última consulta e ainda não foram lidas. A primeira consulta
depois de iniciar só anota onde cada caixa está, então reiniciar nunca reenvia
e-mail antigo. Com vários workers, só um processo vigia (por um arquivo de
trava em `data_dir`).

O push leva o nome de quem enviou, o assunto e o número de não lidas para o
ícone. Ele viaja cifrado de ponta a ponta (Web Push, RFC 8291) pelo serviço de
push do fabricante do navegador (Apple, Google, Mozilla).

## O que fica guardado, e onde

Em `data_dir/mailgrant.db` (SQLite):

- a chave pública e o nome de cada passkey, nunca a chave privada;
- sessões (hash do cookie), convites (hash), desafios do WebAuthn (minutos);
- inscrições de push e suas escolhas de notificação;
- a chave que assina os pushes (VAPID), criada no primeiro uso;
- o histórico da tela de Agentes: agente, ação, caixa, UID, destinatários,
  resultado (nunca assunto nem corpo), mantido por 180 dias;
- a posição do vigia em cada caixa.

Os e-mails continuam nos seus servidores IMAP.

## Segurança

- **Só passkey.** WebAuthn com verificação do usuário obrigatória. Sem senha,
  sem e-mail de recuperação.
- **Convites de uso único e com validade.** Guardados como hash.
- **Cookie de sessão** aleatório, `HttpOnly`, `Secure`, `SameSite=Strict`,
  restrito a `/app`. Toda alteração também exige o cabeçalho `X-Mailgrant` e a
  `Origin` certa.
- **As mesmas regras dos agentes.** A pessoa logada recebe permissão por
  `web.user`; toda ação passa pelas mesmas checagens e pela mesma auditoria.
- **E-mail é texto.** O corpo aparece como texto (com links clicáveis), o HTML
  nunca é interpretado, anexos sempre baixam.
- **CSP rígida**: nada é carregado de outra origem (as fontes vêm junto), sem
  script ou estilo inline, sem iframes.
- O token de um agente não abre o app web, e a sessão do app não abre a API
  MCP/REST.

## Como desligar

Tire a seção `web:` do config, ou mantenha e escreva:

```yaml
web:
  enabled: false
  origin: https://mail.exemplo.com.br
```

Reinicie. O `/app` some, nada é vigiado, o banco fica como está (apague o
`data_dir` se quiser se livrar dele). Os agentes não são afetados em nenhum dos
casos.

## Problemas comuns

| Sintoma | Causa |
|---|---|
| "Convite inválido, já usado ou vencido." | Convite vale uma vez, pelos minutos definidos (30 por padrão). Rode `mailgrant invite` de novo. |
| "Código de configuração errado." | O código digitado não é o do `MAILGRANT_SETUP_CODE` (maiúsculas contam). |
| A tela de entrada não pede código | Já existe passkey, ou a variável não chegou ao container: reinicie depois de criá-la. |
| A passkey falha na hora | A página não está no `origin` configurado (outro endereço, ou http). |
| Não aparece "Ativar notificações" no iPhone | Abra o app pelo ícone da Tela de Início, não pelo Safari. |
| Um aparelho parou de receber | O serviço de push descartou a inscrição (app removido, permissão revogada). Ligue de novo nesse aparelho. |
| E-mail novo nunca notifica | A caixa está desligada em Ajustes, ou `poll_seconds` está alto; procure avisos `watcher:` no log. |
| Tela de Agentes vazia | O histórico começa quando o app é ligado; o que veio antes está só no log. |
