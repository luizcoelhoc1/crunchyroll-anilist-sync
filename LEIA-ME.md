# Crunchyroll → AniList — Python

**Instalador MSI:** no repositório, execute `task compile` no Windows x64 com Task e Python 3.10–3.15 de 64 bits. O resultado fica em `dist/CrunchyrollAniListSync-1.6.0-x64.msi`; a versão pode ser alterada com `task compile VERSION=1.6.1`. Quem instala o MSI abre o app pelo menu Iniciar e não precisa instalar Python. Na versão instalada, o `.env` opcional e os relatórios ficam em `%LOCALAPPDATA%\CrunchyrollAniListSync`, preservados fora da pasta do programa. **Arquivo → Pasta da execução** abre a pasta de dados quando ainda não há execução. A configuração AniList também continua disponível pela interface.

No Windows, os menus e controles de minimizar/maximizar/fechar compartilham uma única barra. Arraste pelo título para mover a janela ou dê dois cliques para maximizar/restaurar. As contas ficam fixas no rodapé da lateral: clique no avatar Crunchyroll para abrir seu login ou no avatar AniList para iniciar a autorização correspondente. Os menus e itens selecionados usam cores, sem molduras claras.

**Interface escura:** os avatares e estados das contas ficam empilhados na lateral, junto aos atalhos de Revisão, Pendências e Progresso. Os menus **Arquivo**, **Contas**, **Sincronizar** e **Ajuda** ficam no topo. **Arquivo → Pasta da execução** abre os relatórios. **Opções avançadas** abre uma janela separada com os métodos alternativos de conexão. Reabra **Iniciar.cmd** depois de atualizar os arquivos para carregar a nova interface.

**Login direto no aplicativo:** **Entrar no Crunchyroll** pede e-mail e senha em campos locais, depois mostra os perfis retornados pela API. Não abre navegador. **Autorizar AniList** continua usando o navegador habitual. O Windows pode lembrar os tokens e o app renova o acesso Crunchyroll automaticamente. Navegador e extensão ficam em **Opções avançadas**.

**Novo:** cartões com nicks e avatares das contas, seleção de itens, edição de alvo e exclusão local do plano. É possível aplicar por lotes e continuar com o restante na mesma prévia. Veja **ATUALIZACAO_1_4.md**.

Programa local para atualizar o progresso e o status da sua lista usando o histórico completo do Crunchyroll, pelas APIs. Depois do login, você pode continuar usando o computador durante a sincronização. O OAuth AniList não controla nem fecha seu navegador pessoal; a confirmação aparece numa aba local.

**Usuário AniList e perfil Crunchyroll são conferidos pela sessão.** Você não precisa digitar os nomes. No login direto, escolha um dos perfis apresentados pelo aplicativo. Eles aparecem em cartões com avatar quando disponível. Nos métodos alternativos com navegador, selecione o perfil no site. Veja **ATUALIZACAO_1_3.md**.

**Versão 1.2:** a comparação automática prioriza o ID da série contido nos links externos do Crunchyroll retornados pela API do AniList, junto com a conferência de temporada e episódios. A prévia e o CSV mostram a origem de cada vínculo. Veja **ATUALIZACAO_1_2.md**.

## Abrir no Windows

1. Extraia **todos os arquivos** do ZIP para uma pasta.
2. Abra **Iniciar.cmd**. Se a associação de Python estiver configurada, também pode abrir **iniciar.pyw**.
3. É necessário **Python 3.10 ou superior com Tkinter**, incluído no instalador padrão para Windows. O motor e a interface usam a biblioteca padrão. Pillow é opcional para avatares JPEG/WebP; **Ativar_avatares.cmd** permite instalar essa opção.

O arquivo principal é `sync_anilist.py`. A interface é `interface.py`. O login direto Crunchyroll e a renovação são implementados na biblioteca padrão Python, sem instalar Rust ou crunchyroll-rs. O AniList abre o navegador habitual. As alternativas de janela própria Crunchyroll aceitam Chrome ou Edge.

## Entrar e manter as contas conectadas

1. Configure o Client ID, o Client Secret e o retorno local no `.env` conforme abaixo. Clique em **Autorizar AniList**. Uma aba abre no Chrome habitual, sem criar outro perfil. Se já estiver conectado ao AniList nesse perfil, autorize o aplicativo. A aba mostra uma confirmação e você pode fechá-la; o programa recebe o código e o troca pelo token automaticamente. Se não houver Client Secret configurado no ambiente ou no arquivo, o programa usa a configuração protegida já salva ou pede o segredo em um campo local.
2. Clique em **Entrar no Crunchyroll**, informe e-mail e senha e clique em **Entrar**. Escolha o perfil e clique em **Usar este perfil**. O app confere a conta e consulta uma página do histórico antes de salvar a sessão. A senha fica somente durante a chamada de autenticação; não é gravada em arquivo, no .env ou nos logs. Deixe **Manter contas conectadas neste Windows** marcado para salvar os tokens protegidos. O AniList já autorizado é preservado.
3. Confira as contas detectadas e gere a prévia. Conectar não modifica sua lista.

As alternativas **Crunchyroll: janela do navegador** e **Tentar Crunchyroll com Edge** ficam em **Opções avançadas**. Se uma delas apresentar um desafio em loop, interrompa a tentativa. Mudar de navegador não garante resolver o bloqueio. A confirmação manual da verificação continua necessária nesses métodos.

A alternativa **Opções avançadas → Crunchyroll: perfil do Chrome (avançado)** usa a conexão consentida do Chrome 144+ ([documentação do Chrome](https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect)). Somente nessa alternativa é necessário habilitar `chrome://inspect/#remote-debugging` e permitir a conexão. A permissão dá acesso de depuração ao perfil; o app acompanha só a aba que criou. Não fecha o navegador nem suas abas anteriores. Ao terminar ou cancelar, fecha a aba criada quando ainda está nas páginas de login/coleta; se você a navegar para outra página, apenas desconecta. Essa configuração não é necessária para o botão principal.

Em **Opções avançadas**, **Conectar pela extensão** mantém o método antigo com a extensão local. As alternativas de janela própria começam na página oficial de login, esperam um acesso com perfil ativo e só então abrem o histórico. Uma resposta 401 no histórico retorna à entrada uma vez; outra recusa interrompe com uma mensagem. O login direto não abre nem recarrega páginas.

Crie um `.env` na mesma pasta de `Iniciar.cmd`, usando `.env.example` como modelo:

```dotenv
ANILIST_CLIENT_ID=55193
ANILIST_CLIENT_SECRET=cole_aqui_o_secret_do_aplicativo
ANILIST_REDIRECT_URI=http://127.0.0.1:8765/anilist/callback
```

O arquivo é lido ao clicar em Autorizar AniList, sem instalar `python-dotenv`. Aceita comentários iniciados por `#`, valores simples ou entre aspas e o prefixo opcional `export `. Não executa comandos, não interpola variáveis e preserva `$`, `#` e `=` dentro de valores entre aspas. Use uma linha por variável. A prioridade é: **ambiente do processo → .env → auth_config.json para os campos públicos antigos → padrões**. Para o segredo, sem valor no ambiente/.env, continuam disponíveis a configuração protegida e o campo da interface. Uma credencial no `.env` tem prioridade sobre uma configuração antiga em memória ou na DPAPI; não é copiada para outro arquivo.

O `.env` é ignorado pelo Git, mas é texto simples. Não o inclua em ZIPs de distribuição. Os tokens das contas continuam fora dele, protegidos pelo Windows. O modelo `.env.example` contém apenas dados públicos e um campo de segredo vazio. No [cadastro do aplicativo AniList](https://anilist.co/settings/developer), o **Redirect URL** precisa ser exatamente `http://127.0.0.1:8765/anilist/callback`. Se esse já é o endereço cadastrado, mantenha-o. O app usa **Authorization Code** (`response_type=code`), confere `state` e recebe o código no retorno local. O processo Python troca esse código por um token via HTTPS no AniList, usando o Client ID e o Client Secret do seu cadastro. O segredo não é colocado na URL nem na página do navegador. O código é removido do endereço da aba; o receptor escuta só em loopback durante o login. Não é possível usar a mesma porta com dois logins simultâneos.

O fluxo anterior `response_type=token` gerou `unsupported_grant_type` no servidor AniList durante o uso real e foi substituído. Não é preciso alterar o retorno local novamente. Para corrigir o Client Secret configurado no arquivo, edite `ANILIST_CLIENT_SECRET` no `.env` e clique novamente em Autorizar AniList. Para a configuração alternativa protegida, use **Opções avançadas → Configurar AniList**. O botão **Abrir cadastro do AniList** leva às configurações do site no navegador habitual. Não envie esse segredo pelo chat nem o coloque em `auth_config.json`.

No diálogo, **Guardar esta configuração protegida pelo Windows** grava apenas a configuração do seu aplicativo pessoal em `%LOCALAPPDATA%\CrunchyrollAniListSync\client-credentials.dat`, criptografada com DPAPI. Desmarcar a opção e salvar remove essa configuração do disco e a mantém só em memória. Essa configuração é separada dos acessos das contas: **Sair / trocar contas** remove os tokens salvos, mas mantém a configuração do aplicativo para o próximo login. Fora do Windows, o Client Secret fica só em memória. Não distribua o arquivo de configuração protegido junto com o código.

Com **Manter contas conectadas neste Windows** marcado, os acessos são protegidos pela DPAPI do usuário atual e gravados em `%LOCALAPPDATA%\CrunchyrollAniListSync\sessions.dat`. Ao reabrir, o programa restaura e confere as contas. **Sair / trocar contas** apaga o login salvo; desmarcar a opção também remove o arquivo e mantém os acessos atuais somente em memória. Isso não encerra as sessões do seu navegador pessoal nem revoga a autorização no site.

O Crunchyroll renova o acesso antes da expiração e tenta uma renovação após HTTP 401 em consultas. No login direto, usa refresh_token; na captura do navegador, usa o cookie etp_rt. Os dois formatos são preservados separadamente e a renovação mantém a conta, o perfil e o identificador de dispositivo. Tokens revogados exigem novo login. HTTP 403 não causa tentativas repetidas. O AniList oferece tokens OAuth de até um ano e não oferece refresh token: ao expirar, autorize novamente.

Uma tela “Performing security verification” com o nome Cloudflare é a verificação do site, não uma confirmação de login. O app aguarda terminar a página de retorno `/callback` antes de navegar para o histórico e identifica respostas marcadas como desafio. A [Cloudflare não oferece suporte a navegadores automatizados para resolver desafios de produção](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/); a janela própria pode ficar em loop mesmo com resolução manual. Se acontecer nos dois navegadores, compare com o login aberto manualmente no navegador habitual. Não há garantia de que alternar Chrome e Edge resolva esse bloqueio.

A alternativa **Crunchyroll: janela do navegador** usa um perfil temporário exclusivo, com gravação de senhas desabilitada. A persistência fica nos tokens e no cookie de renovação protegidos pelo Windows; o perfil temporário é descartado ao fechar. Não usa os bancos de cookies ou senhas do perfil pessoal. A conexão de controle escuta somente em 127.0.0.1. Fora do Windows, os logins ficam em memória; não há persistência DPAPI.

**Interromper** cancela o trabalho em andamento; uma requisição de rede já enviada pode levar até o timeout para retornar. O login cancelado não é salvo. **Cancelar** na escolha de perfil descarta os novos tokens em memória. Nas alternativas de navegador, o app fecha a janela própria ou apenas sua aba criada no modo de perfil normal. O OAuth AniList não fecha a aba do navegador habitual.

## Conectar pela extensão Chrome (alternativa)

Abra **Opções avançadas → Instalar extensão (opcional)**. No Chrome, ative o **Modo do desenvolvedor** em **chrome://extensions**, clique em **Carregar sem compactação** e selecione a pasta **extensao_chrome** do pacote. Use o mesmo perfil do Chrome em que suas contas estão conectadas. Mantenha essa pasta no lugar depois de carregar a extensão.

Depois, clique em **Opções avançadas → Conectar pela extensão**. A extensão abre duas abas de apoio em segundo plano e envia os acessos diretamente para a janela Python. Se um site pedir, faça login ou selecione no Crunchyroll o perfil cujo histórico deseja usar. Aguarde o recebimento dos acessos e clique em **Gerar prévia**. Nenhuma mudança na lista é aplicada ao conectar.

Veja **CONEXAO_CHROME.md** para o passo a passo e funcionamento da conexão local. Não precisa copiar tokens manualmente. O botão se transforma em **Cancelar conexão** enquanto aguarda; a conexão expira em 3 minutos e fecha após receber os dois acessos. Quando a captura Crunchyroll inclui `etp_rt`, o app pode lembrar e renovar essa sessão, após conferir a conta e o perfil, sem alterar as permissões da extensão. Sem esse cookie, o acesso é temporário. O acesso web AniList fica só em memória; o OAuth já autorizado é preservado.

## Fornecer os acessos manualmente (alternativa)

Na tela de login, clique em **Opções avançadas** para abrir os botões **Colar acesso** e **Digitar token**. Essas opções ficam recolhidas por padrão e desaparecem quando as contas são conectadas.

Você também pode copiar uma requisição autenticada de cada serviço. Cole **diretamente na janela do programa**; não envie esses dados por mensagem.

### Crunchyroll

1. No Chrome já conectado, selecione o perfil cujo histórico deseja usar.
2. Aperte **F12** e abra **Network / Rede**.
3. Abra a página de **Histórico** do Crunchyroll. No filtro da aba Network, procure `watch-history`. Se necessário, recarregue a página.
4. Clique com o botão direito na requisição cujo endereço contém `/content/v2/.../watch-history`.
5. Escolha **Copy / Copiar → Copy as fetch (Node.js)**. Em versões antigas, pode aparecer **Copy as Node.js fetch**.
6. Na janela Python, clique em **Colar acesso** na linha Crunchyroll.

Não precisa rolar todo o histórico: o programa percorre as páginas da API. Copie uma requisição recente e gere a prévia logo depois, pois a sessão do Crunchyroll pode expirar rapidamente.

O programa identifica o perfil ativo pelo **profile_id** do token e busca o nome correspondente na API. Você não precisa preencher nome ou ID de perfil. Quando o nome não estiver disponível, o ID aparece na prévia. A API precisa aceitar a sessão para coletar o histórico. Se o token não identificar o perfil ativo, conecte novamente depois de selecionar o perfil no navegador.

### AniList

1. No Chrome conectado ao AniList, abra **F12 → Network / Rede**.
2. Filtre por `graphql` e abra sua lista de animes ou recarregue a página.
3. Copie uma requisição **POST** para **https://anilist.co/graphql** usando **Copy as fetch (Node.js)**.
4. Na janela Python, clique em **Colar acesso** na linha AniList.

A cópia precisa incluir os headers **Cookie** e **X-CSRF-TOKEN**. Se o Chrome colocar o Cookie em um comentário, copie o texto inteiro, incluindo esse comentário. A opção destinada ao navegador pode omitir o Cookie; prefira a opção Node.js. Não é preciso instalar Node.js: o programa apenas lê o texto, sem executar JavaScript.

Outra opção é **Digitar token**, usando um token **OAuth do AniList** que você já tenha. O token CSRF do site não é um token OAuth. Para gerar seu próprio OAuth, consulte a [documentação oficial](https://docs.anilist.co/guide/auth/).

Os acessos manuais e o acesso web AniList recebido pela extensão ficam só em memória, sem renovação automática. O Crunchyroll recebido pela extensão pode ser protegido e renovado se incluir o cookie persistente; sem ele também fica só em memória. Para o AniList, prefira **Autorizar AniList**. Nenhum método grava credenciais nos backups, relatórios ou mapeamentos.

## Sincronizar

1. Com os acessos carregados, confira os nicks detectados nos cartões e clique em **Gerar prévia**.
2. Confira **Revisar plano** e **Pendências e itens ignorados**. Essa etapa só consulta as APIs.
3. Use as caixas **Aplicar** ou o menu **Selecionar** para escolher o lote. **Editar alvo** muda status/progresso; **Comentar episódio** permite incluir uma resposta na atividade quando o avanço for de exatamente 1 episódio. No menu **Plano**, **Excluir do plano** retira linhas localmente e **Restaurar plano** desfaz a revisão local dos itens restantes.
4. Clique em **Aplicar selecionados (N)** e confirme a conta e a quantidade.
5. Aguarde a conferência. Os itens restantes continuam disponíveis para outro lote. **Abrir pasta da execução** mostra os relatórios.

Durante a consulta e a aplicação, você pode usar outros programas. Evite editar a mesma lista do AniList enquanto a aplicação estiver em andamento. A lista é relida antes da aplicação; se uma entrada a alterar mudou desde a prévia, o programa pede uma prévia nova.

Na tela de login, **Importar histórico JSON** permite usar uma exportação completa que você já tenha, inclusive o arquivo de histórico coletado na conversa anterior. Nesse caso não precisa do acesso ao Crunchyroll; ainda precisa do acesso ao AniList. **Usar API** volta à coleta online.

## O que é considerado

- Só episódios com `fully_watched: true` contam. Apenas abrir um episódio não avança a lista.
- Dublagens repetidas não somam episódios.
- O avanço segue os episódios completos em sequência. Lacunas ficam no relatório; um progresso já registrado no AniList pode cobri-las.
- Progresso maior e entradas concluídas são preservados.
- Status Abandonado, Em pausa e Reassistindo são mantidos em avanços parciais; uma sequência concluída pode marcar Concluído.
- Notas, observações, privacidade, repetições, datas e listas personalizadas não fazem parte das alterações propostas. As datas existentes são reenviadas para evitar preenchimento automático e todos esses campos são conferidos ao final.
- Temporadas, partes e OVAs usam correspondências separadas. Links de streaming sozinhos não são usados como prova da temporada.
- Casos sem identificação segura ficam pendentes. Para novos grupos sem regra, o ID nos links Crunchyroll tem prioridade. Temporada, parte, formato e numeração também precisam ser compatíveis.
- Quando o ID confirma a série, um rótulo explícito de temporada permite diferenças de tradução no nome. Sem link utilizável, a alternativa exige título exato e único. Um link que aponta explicitamente para outra série impede essa alternativa.
- A busca também consulta uma rodada de prequelas e sequelas dos resultados. Mapeamentos conferidos continuam tendo precedência. A coluna **Correspondência** e o campo **matches** no plano mostram a evidência.

## Arquivos gerados

A revisão automática usa **revisao.json**, **plano-revisado.json** (somente marcados) e **alteracoes-revisadas.csv**. Cada aplicação parcial tem sua própria subpasta em **aplicacoes/**, com plano do lote, backup, diário e verificação. Os arquivos abaixo descrevem a prévia original e os relatórios dentro de cada pasta de aplicação.

### Comentário na atualização de um episódio

Selecione uma linha com aumento de exatamente 1 episódio (por exemplo, 3 → 4) e clique em **Comentar episódio**. O mesmo campo aparece em **Editar alvo**. Escreva de 2 a 8000 caracteres e salve no plano. Deixar em branco remove o comentário. A coluna **Comentário na atividade** mostra o texto; salvar a revisão não publica nada. A confirmação de **Aplicar selecionados** informa quantos comentários serão enviados no lote.

Após conferir a gravação do progresso, o app compara as atividades daquele anime antes e depois da alteração. Se encontrar uma única atividade nova ou atualizada que corresponda ao episódio, envia o texto como resposta, pelo recurso [SaveActivityReply do AniList](https://docs.anilist.co/reference/mutation). Isso não modifica as observações pessoais da lista nem cria uma publicação de status separada. O AniList pode agrupar episódios na mesma atividade, e a resposta ficará nessa atividade atualizada.

Se a atividade não aparecer, estiver bloqueada ou houver ambiguidade, o progresso permanece aplicado e o comentário fica pendente. O resultado aparece no status e em **comentarios.json**, com texto e link da atividade quando identificado. Se a conexão falhar ao publicar, o app consulta as respostas para conferir o resultado e não repete o envio incerto. Confira a atividade antes de publicar manualmente um comentário pendente. Reaplicar um progresso já atualizado não envia o comentário novamente.

Comentários são salvos nos arquivos locais de revisão e do lote. Aumentar o alvo para mais de 1 episódio remove o comentário dessa alteração. Ao aplicar um avanço parcial, o texto não é reaproveitado automaticamente no restante do plano.

Cada execução fica em **execucoes/AAAAMMDD-HHMMSS-…/**, dentro da pasta do programa.

| Arquivo | Conteúdo |
| --- | --- |
| plano.json | Alterações propostas e pendências |
| alteracoes.csv | Comparação antes/depois, com links para o AniList |
| resumo.md | Resumo da prévia |
| anilist-antes.json | Cópia da lista antes da prévia |
| historico-crunchyroll.json | Histórico coletado ou importado |
| backup-aplicacao-….json | Nova cópia da lista imediatamente antes das gravações |
| diario-aplicacao.jsonl | Tentativas e gravações confirmadas, salvas a cada entrada |
| verificacao.json | Conferência final do resultado |
| comentarios.json | Textos dos comentários, publicações confirmadas e pendências do lote |
| anilist-depois.json | Cópia da lista após a aplicação |
| execucao-interrompida.json | O que foi confirmado ou ficou incerto em uma interrupção |

Os backups contêm sua lista e suas observações pessoais. O ZIP distribuído não contém seu histórico, backups pessoais ou credenciais.

**Interromper** encerra a operação entre requisições. Uma requisição em andamento pode levar até cerca de 40 segundos para responder. Gravações já feitas permanecem na sua conta; o diário permite conferi-las. Em uma falha de conexão durante uma gravação, o programa consulta o resultado antes de continuar, sem repetir cegamente o envio. Gere outra prévia para retomar. Reexecutar a comparação não deve duplicar entradas nem reduzir progresso. Não há restauração automática do backup.

## Mapeamentos de temporadas

O arquivo **mapeamentos_lumimao.json** contém 113 grupos de origem, com 121 regras de correspondência, além das exclusões conferidas. São IDs de catálogo e regras de numeração; não contém credenciais.

Ele cobre os casos conferidos do seu histórico, incluindo temporadas divididas em partes, numeração acumulada, episódio zero e especiais separados. Para temporadas novas ou correspondências pendentes, edite esse JSON e gere outra prévia. O relatório de pendências informa a chave `source_key`.

Exemplo de estrutura (IDs abaixo são ilustrativos; substitua por IDs reais):
```json
{
  "schema_version": 1,
  "groups": {
    "SERIE|TEMPORADA": {
      "title": "Nome do anime",
      "rules": [
        {"mediaId": 123, "mode": "ep", "lo": 1, "hi": 12, "offset": 0},
        {"mediaId": 456, "mode": "ep", "lo": 13, "hi": 24, "offset": 12}
      ]
    }
  }
}
```

`ep` lê o número exibido do episódio; `seq` lê a posição na temporada, útil para episódio zero; `one` representa um filme/especial de um episódio. `lo` e `hi` limitam a numeração de origem. `offset` é subtraído para obter o episódio local no AniList. `title` pode conter uma expressão regular para distinguir um especial. Não crie duas regras que atribuam o mesmo episódio a animes diferentes.

Para ignorar um grupo, use `"skip_reason": "Motivo"` no lugar de `rules`.

## Linha de comando

Abra um terminal na pasta do programa:

```powershell
# Interface
python sync_anilist.py

# Prévia pelas APIs; solicita os tokens sem mostrá-los na tela
python sync_anilist.py preview

# Usar histórico completo exportado, com AniList autenticado
python sync_anilist.py preview --history "C:\caminho\historico-crunchyroll.json"

# Aplicar somente o plano revisado/selecionado que você já conferiu
python sync_anilist.py apply --plan "execucoes\PASTA\plano-revisado.json" --yes

# Testes com dados fictícios, sem consultar ou alterar contas
python -m unittest discover -s tests -v
```

Opções da prévia: **--user**, **--profile**, **--account-id**, **--mappings** e **--out**. **--user** e **--profile** são verificações opcionais; sem elas, o programa detecta a conta e o perfil automaticamente. Para um token bruto do Crunchyroll sem identificação de conta nos claims, informe **--account-id**.

Para uma cópia Fetch com várias linhas, prefira a interface. A CLI também aceita os acessos pelas variáveis de ambiente **CRUNCHYROLL_AUTH** e **ANILIST_AUTH**; não coloque credenciais no código ou em argumentos de comando.

Há um modo de comparação sem conexão:

```powershell
python sync_anilist.py preview --history historico.json --snapshot anilist-antes.json --catalog catalogo.json --out previa-offline
```

O catálogo é uma lista JSON de objetos Media do AniList, com IDs, títulos, formato e quantidade de episódios. Pode repetir **--catalog** para carregar vários arquivos. Uma prévia offline serve para análise e **não pode ser aplicada**; gere uma prévia autenticada atual para gravar.

## Sessão expirada ou API indisponível

Se a renovação automática falhar, use **Entrar no Crunchyroll** novamente. Para OAuth AniList expirado, use **Autorizar AniList**. Nos métodos manuais, copie uma requisição nova. Se o perfil não puder ser conferido, selecione o perfil correto e conecte novamente. Se o site recusar clientes Python, é possível importar uma exportação completa do histórico e usar OAuth do AniList.

O Crunchyroll usa uma API interna do site, que pode mudar ou recusar requisições externas, inclusive na renovação. A sessão web do AniList também depende do site; o novo login usa OAuth oficial. O programa interrompe quando encontra formato inesperado, paginação incompleta ou conta/perfil diferente. Gravações não são repetidas automaticamente por falha de autenticação.

## Validação desta versão

Veja **VALIDACAO.md**. Foram usados testes automatizados e uma comparação offline com os dados já coletados. A aplicação Python não fez uma nova gravação autenticada nas suas contas durante essa validação.

Referências: [autorização AniList por código](https://github.com/AniList/docs/blob/master/docs/guide/auth/authorization-code.md), [limites da API](https://docs.anilist.co/guide/rate-limiting), [Network do Chrome](https://developer.chrome.com/docs/devtools/network/reference/).
