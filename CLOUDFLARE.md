# Login público AniList com Cloudflare Workers Free

O serviço mantém o Client Secret no Cloudflare. O instalador inclui somente o Client ID e o endereço HTTPS público do Worker. Quem baixar o app usa **Autorizar AniList**, sem configurar `.env` nem informar o Client Secret.

## Publicar pela primeira vez

1. Crie uma conta [Cloudflare](https://dash.cloudflare.com/sign-up) e mantenha **Workers Free**. Não é necessário domínio próprio nem plano pago.
2. Instale Node.js 22 ou superior, além do Python e Task já usados pelo projeto.
3. Mantenha `ANILIST_CLIENT_ID` e `ANILIST_CLIENT_SECRET` no `.env` local. Esse arquivo continua ignorado pelo Git e excluído do instalador.
4. Execute `task auth:login` e autorize o Wrangler no navegador. A credencial Cloudflare fica protegida no cofre do Windows; a primeira execução pode instalar o componente de keyring solicitado pelo Wrangler.
5. Execute `task auth:deploy`. O comando publica o Worker, envia as chaves AniList pelo stdin do Wrangler, verifica `/health` e grava somente os campos públicos em `auth_config.json`. A chave de assinatura das tentativas de login é gerada no primeiro deploy e preservada nos seguintes.
6. Copie o **Redirect URL** mostrado no terminal, no formato `https://crunchyroll-anilist-auth.SEU-SUBDOMINIO.workers.dev/v1/callback`, para o cadastro do mesmo aplicativo no [AniList](https://anilist.co/settings/developer). O endereço precisa ser idêntico. O app continua recebendo o retorno final em `127.0.0.1` automaticamente.
7. Execute pelo código e confira **Autorizar AniList**. Depois use `task compile` para gerar e publicar o instalador com o endereço público configurado.

Se você tiver várias contas Cloudflare, selecione a conta Free usando `CLOUDFLARE_ACCOUNT_ID` no ambiente antes do deploy. O comando não altera planos ou assinaturas e não cria bancos de dados, KV ou Durable Objects.

## Funcionamento

O app inicia uma tentativa de dez minutos, gera uma prova aleatória local e envia somente seu hash ao Worker. O Worker assina os dados da tentativa e o navegador abre o AniList. Após consentir, o AniList retorna ao Worker, que confere a assinatura e encaminha o código ao endereço local previamente validado. O app apresenta a prova original ao Worker, que troca o código no endpoint oficial do AniList usando o segredo do servidor. Apenas o token do usuário volta ao app, que ainda confirma a identidade na API antes de salvar a sessão protegida no Windows.

A prova protege a comunicação app–Worker; ela não pressupõe suporte PKCE do AniList. O segredo não aparece em URLs, respostas públicas ou no instalador. Códigos e tokens não são persistidos pelo Worker. Os logs de execução do Worker ficam desativados, e as respostas usam `no-store` e `no-referrer`. Os retornos são aceitos somente em `http://127.0.0.1:PORTA/anilist/callback`, nunca em um destino arbitrário.

O serviço usa um limite aproximado de 60 chamadas por minuto por IP e ponto de presença. Redes compartilhadas podem atingir esse limite juntas. Há também a cota da conta Workers Free: ao esgotá-la, novas autorizações falham até sua renovação, sem migração automática para plano pago. Os limites vigentes estão na [documentação Cloudflare](https://developers.cloudflare.com/workers/platform/limits/#daily-requests).

## Alternativa local

Sem `anilist_auth_service_url` em `auth_config.json`, permanece o login direto com segredo local. Para desativar o serviço somente no seu computador, defina `ANILIST_AUTH_SERVICE_URL=` no `.env` ou no ambiente. O Client ID e o Redirect URL registrados no AniList precisam corresponder ao fluxo escolhido; mudar o Redirect URL do cadastro para o Worker pode impedir o login em versões antigas que usavam o retorno local direto.

## Testar

```sh
python -m unittest discover -s tests
node --test tests/test_auth_worker.mjs tests/test_extension.mjs
```

Para validar o pacote do Worker sem publicar:

```sh
npm --prefix cloudflare ci
node cloudflare/node_modules/wrangler/bin/wrangler.js deploy --config cloudflare/wrangler.jsonc --dry-run
```

Os testes usam chaves e contas fictícias. A autorização real exige concluir o login Cloudflare e configurar o Redirect URL no AniList.
