# Crunchyroll → AniList Sync

Aplicativo Python para comparar o histórico do Crunchyroll com sua lista do AniList e aplicar atualizações revisadas.

A interface usa tema escuro inspirado no VS Code, menus no topo e uma lateral com navegação, avatares e estado das contas. **Gerar prévia** e **Aplicar selecionados** ficam em destaque; **Comentar episódio** abre o comentário opcional da atualização. As opções de seleção e restauração ficam nos menus **Selecionar** e **Plano**, acima da tabela.

**Código atual:** AniList no navegador habitual, sessões protegidas no Windows e renovação do Crunchyroll. [Instruções completas](LEIA-ME.md) · [Usar o Chrome já conectado](CONEXAO_CHROME.md)

Baixe o instalador MSI para Windows x64 na [release mais recente](https://github.com/luizcoelhoc1/crunchyroll-anilist-sync/releases/latest). Veja o [histórico de releases](https://github.com/luizcoelhoc1/crunchyroll-anilist-sync/releases) e as [novidades da série 1.6](ATUALIZACAO_1_6.md).

## Usar no Windows

Com o instalador gerado por `task compile`, abra o MSI e use o atalho **Crunchyroll - AniList Sync** no menu Iniciar. A instalação é por usuário e inclui Python, Tkinter e Pillow; não é necessário instalar Python no computador de destino.

Para executar diretamente pelo código:

1. Baixe ou clone o código atual e mantenha todos os arquivos juntos.
2. Instale Python 3.10 ou superior com Tkinter.
3. Abra **Iniciar.cmd**.
4. Clique em **Autorizar AniList** e autorize na aba do navegador habitual.
5. Clique em **Entrar no Crunchyroll**, informe e-mail e senha no próprio aplicativo e escolha seu perfil. O programa confere a conta e o acesso ao histórico antes de salvar os tokens. Deixe **Manter contas conectadas neste Windows** marcado para restaurar e renovar a sessão nas próximas execuções.
6. Revise, selecione os itens e aplique o lote desejado.

O login direto Crunchyroll é uma integração não oficial implementada em Python no projeto, sem instalar a biblioteca de referência. A API pode recusar o cliente, exigir uma confirmação ou bloquear a chamada; nesses casos o app informa o erro e não repete a senha automaticamente. Os métodos com navegador e extensão continuam em **Opções avançadas**.

Para distribuir o aplicativo já configurado, use o [serviço gratuito de autorização no Cloudflare](CLOUDFLARE.md). Nesse modo, o segredo fica no Worker e o instalador leva apenas a configuração pública. As instruções de `.env` abaixo também permitem usar o login direto local.

Para o login direto, configure o AniList em um arquivo `.env` na pasta do programa (modelo em [.env.example](.env.example)):

```dotenv
ANILIST_CLIENT_ID=55193
ANILIST_CLIENT_SECRET=cole_aqui_o_secret_do_aplicativo
ANILIST_REDIRECT_URI=http://127.0.0.1:8765/anilist/callback
```

O Redirect URL no cadastro AniList deve ser idêntico. O `.env` é ignorado pelo Git e não exige instalar biblioteca adicional. Ele guarda o segredo em texto simples; os tokens das contas continuam protegidos pelo Windows. O app usa variáveis do ambiente antes do `.env`; sem segredo nessas fontes, permite usar a configuração protegida da interface. `auth_config.json` continua como alternativa para os campos públicos antigos.

O login AniList usa autorização por código no navegador habitual. O Crunchyroll recebe e-mail e senha na interface local e envia a autenticação somente ao domínio oficial por HTTPS. A senha não é salva; os tokens ficam protegidos pelo Windows. Não exige navegador, extensão ou debug para essa tentativa de login. Pillow é opcional para os avatares; **Ativar_avatares.cmd** instala essa dependência.

## Recursos

- Coleta paginada pela API, sem rolar o histórico na tela.
- OAuth AniList em uma aba do navegador habitual, sem copiar tokens ou abrir outro perfil.
- Login direto Crunchyroll por e-mail/senha, seleção de perfil e renovação por refresh token; senha não persistida.
- Contas lembradas entre execuções com DPAPI do usuário Windows e opção de remover o login salvo.
- Renovação automática do Crunchyroll, com conferência da conta e do perfil; OAuth oficial no AniList.
- Identificação de contas, nicks e avatares.
- Correspondência por mapeamentos conferidos e IDs dos links Crunchyroll, com verificação de temporada e parte.
- Prévia com marcação, edição de progresso e exclusão local de itens do plano.
- Comentário opcional na atividade AniList para avanços de exatamente 1 episódio, revisado antes de aplicar.
- Aplicação parcial, backups, diário de operações e verificação final.
- Preservação de notas, observações, privacidade, datas e progresso maior.

## Desenvolvimento

Para compilar e publicar no Windows x64, tenha [Task](https://taskfile.dev/docs/installation), Git e Python 3.10–3.15 de 64 bits com Tkinter no `PATH`. O remoto `origin` deve apontar para o GitHub, e a branch local deve estar atualizada com a remota. Use a autenticação já configurada no Git ou defina `GH_TOKEN`/`GITHUB_TOKEN` com permissão **Contents: write** no repositório:

```sh
task compile
```

A tarefa incrementa automaticamente o último número da versão registrada em [`VERSION`](VERSION), compila e verifica **`dist/CrunchyrollAniListSync-X.Y.Z-x64.msi`**, salva a nova versão, cria um commit com as alterações não ignoradas pelo Git e cria a tag `vX.Y.Z`. Depois envia a branch e a tag para `origin`, cria a release com notas automáticas e anexa o MSI e `SHA256SUMS.txt`. A release só se torna pública depois de conferir os anexos. A publicação usa a [API oficial de releases do GitHub](https://docs.github.com/en/rest/releases/releases) e não exige GitHub CLI.

Se o envio falhar, execute `task compile` novamente: a tarefa retoma a mesma versão a partir de `build/pending-release.json`, sem recompilar ou aumentar a versão. Preserve o código e o instalador até concluir essa publicação. Alterações no código durante a compilação interrompem a publicação para preservar a correspondência entre o instalador e a tag. Tags e anexos existentes não são sobrescritos.

Para gerar somente o build local, sem commit, tag ou publicação:

```sh
task compile PUBLISH=false
```

Os dois modos criam/reutilizam `.venv-build` e instalam as ferramentas de `requirements-build.txt`. A nova versão só é salva em `VERSION` após compilar e verificar o pacote com sucesso. Na primeira execução é necessário acesso à internet para baixar as dependências. Não exige WiX nem SDK .NET. O executável também fica em `build/app/CrunchyrollAniListSync.exe` e precisa dos arquivos ao seu lado.

Para escolher uma versão específica, maior que a atual:

```sh
task compile VERSION=1.7.0
```

No modo local, inclua o arquivo `VERSION` atualizado no seu próximo commit. A tarefa confere a estrutura do MSI e abre/fecha uma instância com dados temporários vazios; não instala o MSI nem usa logins reais durante essa verificação. Feche uma cópia de teste de `build/app` antes de recompilar. Compilações simultâneas são recusadas; se o processo for encerrado à força, remova `build/.compile.lock` depois de conferir que ele terminou, preservando `build/pending-release.json` para retomar um envio pendente.

Somente os arquivos públicos listados em `packaging/windows.py` entram no pacote. O `.env` pessoal, sessões e relatórios não são incluídos. Na versão instalada, configuração `.env`, logs e relatórios ficam em **`%LOCALAPPDATA%\CrunchyrollAniListSync`**; o modelo `.env.example` fica na pasta de instalação. As sessões continuam protegidas na mesma pasta de dados já usada pelo programa. Executando pelo código, o `.env` e a pasta `execucoes` continuam na raiz do projeto.

Testes de desenvolvimento:

```sh
python -m unittest discover -s tests -v
node --test tests/test_extension.mjs
```

Node.js é necessário para os testes JavaScript e para publicar o serviço opcional de autorização; nesse caso, siga [CLOUDFLARE.md](CLOUDFLARE.md). O aplicativo desktop não exige Node.js. Veja [VALIDACAO.md](VALIDACAO.md) para os testes realizados e seus limites.

## Versões e dados locais

O histórico Git começa no pacote completo preservado da **1.4**, que já reúne os recursos anteriores. A **1.5** tem seu próprio commit e tag. As notas das versões 1.2 e 1.3 documentam a evolução anterior; não existem snapshots completos preservados dessas versões neste repositório.

O repositório contém código, testes, documentação e regras de catálogo. Não inclui tokens, cookies, exportações do histórico nem backups da lista. O arquivo `mapeamentos_lumimao.json` contém IDs públicos e regras de episódios usadas pelo aplicativo.

Quando **Manter contas conectadas neste Windows** está marcado, os acessos dos novos logins ficam criptografados em `%LOCALAPPDATA%\CrunchyrollAniListSync\sessions.dat`, fora do repositório. **Sair / trocar contas** remove esse arquivo. O Crunchyroll recebido pela extensão também pode ser salvo/renovado quando os headers incluem o cookie persistente; o acesso web AniList e os tokens manuais ficam somente em memória. Autorize o AniList primeiro para preservar o OAuth ao conectar pela extensão.

O Client Secret é uma configuração separada: a opção de guardá-lo no diálogo usa DPAPI em `%LOCALAPPDATA%\CrunchyrollAniListSync\client-credentials.dat`. Ele não entra no JSON público, na URL do navegador nem nos relatórios. Para substituir ou retirar a configuração salva, use **Opções avançadas → Configurar AniList**; desmarcar a opção de guardar e salvar remove o arquivo e mantém o segredo só nesta execução.

Crunchyroll usa uma API interna sujeita a mudanças. Gere e confira a prévia antes de aplicar alterações.
