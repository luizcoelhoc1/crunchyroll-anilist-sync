# Validação — 02/11/2026

Ambiente: Windows, Python 3.13.3. O código usa apenas a biblioteca padrão e declara compatibilidade com Python 3.10 ou superior; outras versões não foram executadas nesta validação.

## Interface escura — código atual

Revisão visual: barra de título integrada aos menus no Windows, contas ancoradas na base da lateral, divisórias removidas e dropdowns próprios sem moldura nativa. A implementação da área de título segue o [exemplo de frame personalizado da Microsoft](https://learn.microsoft.com/windows/win32/dwm/customframe). Uma instância isolada confirmou maximização, restauração, minimização e redimensionamento, com capturas locais de janelas normal e menor. **222 testes Python passaram, sem ignorados**, incluindo comandos dos menus, fechamento por Escape e cliques nos avatares com login e worker simulados, sem autenticação real.

**220 testes Python passaram, sem ignorados**, após a reorganização visual. Capturas locais de uma instância com dados fictícios foram inspecionadas em 1380 × 900 e 1050 × 720, incluindo login, contas conectadas, plano com três animes, editor de comentário e opções avançadas. A navegação lateral e as abas foram exercitadas preservando o plano. Nenhuma conta real foi acessada ou atualizada.

O tema cobre tabelas, campos, menus, editor e janelas próprias do aplicativo; seletores de arquivos e alertas nativos seguem o Windows. Os testes de Tk agora liberam seus objetos na thread principal antes dos testes de servidores locais, evitando uma falha intermitente de coleta do interpretador Tcl numa thread secundária.

## Comentários em atualizações de um episódio — código atual

A revisão oferece **Comentar** e um campo em **Editar alvo** para avanços de exatamente 1 episódio. O texto é opcional, limitado a 2–8000 caracteres e incluído nos arquivos de revisão e CSV. A aplicação compara atividades antes/depois e publica via `SaveActivityReply` somente após confirmar o progresso, com conta, anime, progresso e atividade única conferidos. Aceita atividade agrupada cujo progresso mudou e atividade de conclusão do último episódio. Ausência, bloqueio ou ambiguidade geram pendência sem desfazer o progresso.

**220 testes Python passaram, sem ignorados**, incluindo a interface Tkinter. Os testes novos cobrem revisão sem publicação, seleção/exportação, limites, retirada de comentário em mudança do alvo e no próximo lote, associação da atividade, duplicidade/ambiguidade, resposta perdida com consulta sem reenvio, erros opcionais preservando a atualização e ausência de consultas extras quando não há comentário. A mutation foi verificada contra a documentação oficial do AniList; nenhuma atividade ou resposta real foi publicada nesta validação. `git diff --check` passou.

## Login direto: correção da validação após escolher o perfil — validação anterior

O login por e-mail/senha passou a retornar os perfis na conta real do usuário, mas a criação de `CrunchyrollSession` recusava o User-Agent da plataforma por conter ponto e vírgula. Esse caractere é normal nos comentários do User-Agent; a validação aplicava a ele a restrição usada para separadores de cookies. A correção permite ponto e vírgula somente nesse campo, mantendo a recusa de quebras de linha e NUL em todos os campos e de separadores nos cookies.

O erro foi reproduzido com tokens fictícios e o User-Agent efetivamente configurado em `cr_direct_login.py`. Os testes de sessão e interface agora usam esse valor, em vez de um User-Agent simplificado. **206 testes Python passaram, sem ignorados**, incluindo seleção de perfil, consulta do histórico antes de salvar, renovação, preservação do AniList e recusa de injeção de headers. A confirmação do login completo na conta real ainda depende de reabrir o programa e tentar novamente. Nenhuma credencial real foi lida nessa validação.

O login direto é uma implementação própria em Python do protocolo observado na referência crunchyroll-rs; não instala nem executa essa biblioteca. E-mail/senha são enviados somente ao endpoint oficial; a senha não é persistida. A sessão usa refresh token com o mesmo dispositivo e valida conta/perfil após renovar. Os métodos antigos com cookie continuam compatíveis. A verificação anterior com dados fictícios encontrou um cliente de plataforma revogado; a identificação atual publicada na referência passou dessa recusa e chegou à recusa de login esperada para os dados fictícios. A implementação continua dependente de uma API não oficial e pode exigir atualização caso o cliente seja revogado novamente.

## Retorno do login e desafio Cloudflare — validação anterior

A captura enviada pelo usuário mostrou uma página de desafio Cloudflare em `/callback`, repetindo tanto no Chrome quanto no Edge. Corrigida a condição que permitia navegar para o histórico ao observar um token de perfil antes de terminar essa página de retorno. Agora aguarda sair de `/callback` (inclusive com barra final) e não avança a partir de `/cdn-cgi/`. Respostas do Crunchyroll com `cf-mitigated: challenge` geram uma orientação específica, sem recarga automática nem interpretação como acesso confirmado.

**187 testes Python passaram, sem ignorados.** Os novos casos verificam que a chegada do token durante o callback não interrompe o retorno e que uma resposta de desafio, mesmo com HTTP 200, não captura a sessão. Uma resposta normal posterior permite continuar. Isso corrige o tratamento do fluxo; **não confirma a resolução do loop real**. A Cloudflare documenta navegadores automatizados como ambientes sem suporte para resolver desafios em produção. A comparação com o navegador habitual do usuário ainda é necessária para investigar a causa.

## Alternativa pelo Edge para investigar o loop de reCAPTCHA — validação anterior

Foi relatado um reCAPTCHA repetindo após a resolução manual na janela própria. A causa não foi confirmada nem o loop reproduzido com uma conta real. A tela de login agora oferece **Tentar Crunchyroll com Edge**, usando outra instância isolada e a mesma captura/persistência da sessão. Se não localizar Edge, informa o problema sem voltar ao Chrome. O carregamento de um iframe reCAPTCHA emite uma orientação uma vez por tentativa, sem recarregar a página, resolver o desafio ou tratar a presença dele como falha.

**185 testes Python passaram, sem ignorados**, incluindo seleção explícita de Edge, ausência de fallback silencioso, mensagem sem recarga, captura da sessão e preservação do AniList pelo botão da interface. Uma instância real de Edge com perfil vazio foi aberta em modo headless, respondeu a um comando local e fechou com remoção do perfil temporário. Esse teste confirma o transporte e a limpeza; não valida o login real nem que o reCAPTCHA aceitará a janela visível.

## Crunchyroll em janela própria como padrão — validação anterior

**Entrar no Crunchyroll** passou a abrir a página oficial em uma janela própria do Chrome/Edge, sem configuração manual de depuração ou extensão. A alternativa de perfil normal ficou em Opções avançadas; tentar novamente no diálogo dessa alternativa mantém o modo escolhido. A persistência usa os tokens e o cookie de renovação protegidos pela DPAPI, enquanto o perfil temporário do navegador é descartado após o login.

**180 testes Python passaram, sem ignorados**, incluindo a interface Tkinter fora do sandbox. Os testes conferem a janela própria como padrão, preservação do AniList, gravação do acesso validado e restauração de uma sessão Crunchyroll expirada com renovação e persistência do cookie rotacionado sem chamar o login. A renovação nesse teste usa respostas fictícias; o login completo na conta real depende da tentativa do usuário. `git diff --check` passou.

## Crunchyroll no último perfil normal do Chrome — validação anterior

O botão principal passou a usar o recurso de conexão com permissão do Chrome 144+. A seleção usa somente o campo de último perfil em `Local State`, sem copiar o perfil ou abrir bancos de cookies/senhas. A conexão é descoberta pelo arquivo `DevToolsActivePort`; ela depende de o usuário habilitar o recurso no próprio Chrome e permitir a conexão. O app não muda essa configuração automaticamente. Cria uma aba com marcador único no perfil selecionado e só se conecta a esse alvo. O modo temporário e a extensão ficam como alternativas em Opções avançadas.

**179 testes Python passaram, sem ignorados.** Os novos casos exercitam seleção do perfil, metadados inválidos, recusa de perfil Convidado/caminhos, falta de configuração sem abrir janela temporária, cancelamento, preservação de arquivos, fechamento exclusivo da aba criada pelo app e ausência de `Browser.close`. Uma aba criada pelo app e depois navegada para outro destino é desconectada e mantida aberta. A interface escolhe o modo normal por padrão e mantém o modo isolado explícito.

Foi exercitada a conexão a uma instância real de Chrome com perfil vazio de teste: a segunda conexão criou/controlou/fechou sua própria aba e preservou a instância, os arquivos e a aba anterior. O perfil de teste usou depuração habilitada na inicialização; **o diálogo de permissão do perfil pessoal e o login real não foram automatizados nem validados nessa prova**. O Chrome pessoal não foi conectado pelo agente. A versão instalada inspecionada foi 156.0.8078.49, compatível com o requisito documentado do recurso.

## Crunchyroll: abrir login antes do histórico — validação anterior

A janela sem extensão começava com perfil temporário vazio, mas abria `/history`. Foi alterada para começar em `https://www.crunchyroll.com/login`, que redireciona para o SSO oficial. Só abre o histórico depois de observar um token com conta/perfil ativo e de a página principal voltar do SSO. Tokens anônimos ou sem perfil não avançam esse fluxo. O acesso ainda depende de resposta bem-sucedida do histórico e posterior conferência no aplicativo.

**168 testes Python passaram, sem ignorados.** Os novos casos cobrem a entrada antes do histórico, headers recebidos fora de ordem, espera durante o SSO, navegação de iframe ignorada, token anônimo/sem perfil, 401 com retorno único ao login, progresso da interface e preservação do AniList já conectado.

Em uma instância real e vazia do Chrome, o endereço oficial abriu a página “Log In” com o campo “Email or Phone Number”. Não foram preenchidos dados nem autenticada uma conta. O login completo, a escolha real do perfil e a coleta do histórico continuam pendentes da tentativa do usuário. A extensão não foi alterada nesta correção.

## Correção HTTP 403 na troca AniList — validação anterior

O 403 foi reproduzido no endpoint real com Client ID, segredo e código fictícios. A requisição padrão de `urllib` recebeu 403; a mesma operação identificada como `CrunchyrollAniListSync/1.0` recebeu 401 `invalid_client`, esperado para esses dados fictícios, demonstrando que chegou à validação normal. O cliente OAuth passou a enviar esse User-Agent explicitamente, como o cliente das consultas já fazia.

**162 testes Python passaram, sem ignorados.** Um teste de regressão usa um servidor HTTP real local que recusa o User-Agent padrão Python e confirma que a troca do aplicativo chega ao token fictício. A mensagem da aba agora diferencia o recebimento do código da validação do acesso no programa. O erro 403 também informa essa distinção, sem expor resposta bruta ou credenciais.

A função de troca corrigida também foi executada uma vez contra o endpoint real com credenciais fictícias e chegou à validação de cliente, sem o bloqueio anterior. A autenticação com as credenciais reais do usuário continua dependendo da nova tentativa no programa; o agente não leu o `.env` nem alterou listas nessa verificação.

## Configuração AniList por .env — validação anterior

**161 testes Python passaram, sem ignorados.** A configuração aceita `ANILIST_CLIENT_ID`, `ANILIST_CLIENT_SECRET` e `ANILIST_REDIRECT_URI`, sem dependências adicionais. Foram exercitados precedência do ambiente sobre `.env` e JSON antigo, aspas, comentários, BOM, valores literais sem execução/interpolação, erro sem exposição do segredo e a ausência do segredo no `repr` da configuração. Na interface oculta, o segredo do `.env` substitui uma configuração antiga sem abrir o diálogo e sem gravar uma cópia na DPAPI.

O `.env` local foi criado com o segredo em branco, sem converter ou exportar credenciais protegidas existentes. Foi conferido que o Git ignora `.env` e permite `.env.example`. As credenciais usadas pelos testes são fictícias e o `.env` real não foi lido durante a suíte. Tokens das contas e a renovação não foram alterados por essa configuração.

## Correção AniList: Authorization Code — validação anterior

Após o uso real retornar `unsupported_grant_type` em `/oauth/authorize` com `response_type=token`, o login foi alterado para `response_type=code`. O retorno local e o navegador habitual permanecem. A troca POST em `/api/v2/oauth/token` envia JSON com `grant_type=authorization_code`, Client ID, Client Secret, código e Redirect URL, conforme a documentação desse fluxo. O Client Secret é informado localmente em campo mascarado; a persistência opcional usa um arquivo DPAPI separado dos tokens das contas.

**152 testes Python passaram, sem ignorados**, e **6 testes JavaScript passaram**. Cobrem retorno de código via HTTP real, validação de `state`, duplicações, erros/cancelamento, configuração local do segredo antes de abrir o login, campo mascarado, cancelamento do diálogo sem salvar, envio do payload correto na troca, recusa de redirecionamentos e mensagens que não expõem código/segredo da resposta do servidor. A DPAPI real foi exercitada com Client Secret fictício: não aparece em texto simples no arquivo, é associado ao Client ID correto e pode ser removido.

Uma instância real do Chrome abriu uma página local com código fictício e confirmou o recebimento e a remoção da query string do endereço. Os testes gráficos e essa instância do Chrome foram executados fora do sandbox, que impede a inicialização gráfica. **A troca autenticada com o Client Secret real do aplicativo não foi executada pelo agente**; ela depende da configuração local e da autorização da conta no programa. Nenhuma lista remota foi alterada nessa validação.

## AniList no navegador habitual e sessão Crunchyroll pela extensão — validação anterior

**145 testes Python passaram, sem ignorados**, e os **6 testes JavaScript da extensão passaram**. O retorno OAuth usa HTTP real em loopback com tokens fictícios: `state`, origem, Host, prazo, cancelamento, duplicações, porta ocupada, payloads inválidos e encerramento do receptor. A abertura do Chrome habitual foi conferida por simulação do launcher, sem flags de perfil temporário; o sistema/navegador escolhe o perfil usado para abrir a aba.

Uma página local foi aberta em uma instância real de Chrome para testar o JavaScript do retorno: um token fictício foi entregue automaticamente e removido do fragmento do endereço. Não foi usado um token de conta real. A interface oculta foi exercitada com restauração das contas, preservação do OAuth AniList durante a conexão pela extensão e gravação da sessão Crunchyroll somente após conferir a identidade por API simulada. O aproveitamento de `etp_rt` dos headers existentes da extensão não altera as permissões dela.

**Limite dessa validação anterior:** os testes de retorno com token fictício não cobriam a aceitação do fluxo implícito pelo AniList. O uso real revelou a recusa e motivou a correção descrita acima. O Redirect URL local permanece `http://127.0.0.1:8765/anilist/callback`. O cadastro externo não foi alterado pelos testes. O cliente público web Crunchyroll não forneceu um fluxo utilizável de autorização por código na consulta realizada; não foi incluído como alternativa de login. Nenhuma conta foi acessada ou lista modificada nessa consulta.

## Login inicial sem extensão — validação anterior

**129 testes Python passaram**, sem testes ignorados, e **6 testes JavaScript da extensão passaram**. A suíte inclui renovação antecipada, rotação do cookie, retorno ao perfil salvo, recusa de outra conta/perfil, nova tentativa única de consulta após 401, ausência de repetição de gravações, retorno OAuth com `state`, captura dos headers em ordens diferentes e remoção do login salvo.

A DPAPI real do Windows foi exercitada com dados fictícios em pasta temporária: gravação sem token/cookie em texto simples, restauração, recusa de conteúdo adulterado e exclusão. Os novos estados da interface foram testados com Tkinter oculto e APIs simuladas: restauração, OAuth expirado, opção de lembrar, saída, acesso não validado e fechamento preservando o login salvo.

Uma instância real do Chrome, com perfil temporário vazio, foi aberta por CDP, navegou para uma página fictícia e foi fechada. A página pública OAuth do Client ID informado abriu o formulário de login do AniList sem erro de cadastro/retorno visível nessa etapa. Nenhuma conta foi autenticada. Chrome e Tkinter precisaram ser executados fora do sandbox de desenvolvimento, que impede a inicialização gráfica; a suíte completa passou nesse ambiente.

**Limite dessa validação anterior:** o consentimento OAuth após login, a captura de uma sessão real Crunchyroll e os grants de renovação da API interna ainda precisavam ser conferidos com as contas no programa. O fluxo anterior do AniList usava retorno PIN em perfil temporário; foi substituído pelo retorno local descrito acima. A API interna e os bloqueios do Crunchyroll podem mudar; as respostas autenticadas de renovação foram simuladas. Não houve gravações remotas nas contas. A compatibilidade com Edge e outros sistemas não foi executada nesta validação.

## Atualização 1.5 — controles de login

Alteração de interface. Foram verificados os estados de login com Tkinter oculto e APIs simuladas: painel de token inicialmente recolhido, abertura/fechamento, ocultação após identificar as contas, prévia mantendo os nicks, troca de conta e erro de autenticação permitindo nova tentativa. O fluxo de PNG/JPEG e três lotes parciais da versão anterior foi repetido com sucesso. O motor e a extensão não foram alterados; não houve operações nas contas reais.

## Atualização 1.4 — contas e revisão por lotes

**85 testes passaram:** os 63 anteriores do motor e 22 novos (14 de revisão/aplicação e 8 de imagens/identificação). O fluxo gráfico foi exercitado com a janela oculta, PNG/JPEG fictícios e APIs simuladas: nicks, dois avatares, marcação, edição de progresso, exclusão/restauração e três lotes. Foram conferidos a preservação de campos pessoais, o progresso restante retornando desmarcado e as pastas separadas por lote. A exportação respeita a seleção; aplicar revisao.json diretamente é recusado.

A regressão offline manteve os 83 alvos anteriores e zero alterações na repetição. Não foram usadas sessões reais nem feitas novas gravações nas contas. As imagens reais dos serviços não foram baixadas durante esses testes; o HTTP das imagens foi simulado. O suporte Pillow foi testado nesta instalação, e é opcional para o uso geral do programa.

## Atualização 1.3 — identificação automática

**63 testes do motor passaram nesta atualização:** os 53 anteriores e 10 de identidade. São exercitados Viewer, seleção pelo ID ativo do token, perfis em outra posição da lista, nomes diferentes dos padrões antigos, consulta de nome indisponível e token sem perfil. As verificações de conta/perfil esperados continuam opcionais na CLI.

A janela oculta foi testada com APIs simuladas em duas origens: coleta pela API e importação JSON. Os nomes foram preenchidos sem controles editáveis, o plano continuou válido após o preenchimento e a identidade foi limpa ao trocar os acessos. A regressão offline manteve os 83 alvos e zero alterações na segunda comparação. Os textos da conexão foram ajustados; o protocolo da extensão não mudou.

## Atualização 1.2 — links externos

**53 testes do motor passaram nesta atualização:** 35 existentes e 18 novos. Os novos casos cobrem normalização de URLs, priorização por ID, links contraditórios, tradução do nome com temporada explícita, temporadas compartilhadas, partes em números romanos, filmes/especiais, numeração cumulativa, evidências no plano e consulta de prequelas/sequelas.

A regressão offline manteve os mesmos 83 alvos e zero novas alterações na segunda execução simulada. Foram verificados o CSV com a coluna Correspondência e a janela Tkinter oculta exibindo ID Crunchyroll para uma correspondência automática fictícia. O código da ponte/extensão não foi alterado nesta versão; os resultados abaixo referentes a ela são da validação da versão 1.1.

## Testes automatizados da versão 1.1

**Na versão 1.1, 50 testes Python passaram**, sem conexão com os serviços e sem alterar contas. Os testes novos exercitaram a conexão HTTP real em 127.0.0.1, com credenciais fictícias.

Cobertura dos casos relevantes:
- episódios parciais, lacunas, duplicações de áudio e progresso existente;
- temporadas divididas, OVAs, numeração cumulativa e regras conflitantes;
- preservação de progresso maior, concluídos e campos pessoais;
- sessão expirada, perfil incorreto, paginação incompleta e destino de API inesperado;
- limitação de tentativas em consultas e ausência de repetição cega de gravações;
- plano desatualizado, falha de conexão após gravação, diário de tentativas e confirmação;
- bloqueio de aplicação de plano offline e reexecução sem gravações duplicadas.

Comando na pasta do programa:

```
python -m unittest discover -s tests
```

## Extensão e conexão local — versão 1.1

**6 testes JavaScript passaram**, incluindo um fluxo simulado de Chrome que emparelha, abre abas inativas, captura os dois serviços, fecha as abas de apoio e evita armazenar credenciais. Foram testadas a restrição às abas criadas pela extensão, a validação de origem, o prazo da chave, o filtro de headers e a recusa de remetentes inesperados.

O servidor local foi testado com HTTP real: chave obrigatória, origem/Host conferidos, prazo, entrega dos dois acessos, pedidos duplicados e corpos inválidos. Os testes da extensão usam as APIs Chrome simuladas; ela ainda precisa ser carregada uma vez no Chrome pelo usuário. Não houve captura de sessões reais durante essa validação.

Comando opcional para desenvolver/testar a extensão (exige Node.js, que não é necessário para usar o programa):

```
node --test tests/test_extension.mjs
```

## Regressão com o histórico já coletado

Comparação local com **2.823 registros**, distribuídos em **140 grupos**, e a cópia anterior de **881 entradas** do AniList:

- Mesmos **83 alvos** do plano anteriormente conferido, com IDs, status e progresso exatamente iguais.
- **72 adições**, **11 atualizações**; **57** das alterações com status Concluído.
- **17 ocorrências de pendência** na versão Python, incluindo episódios/especiais fora das regras e lacunas. Pendências são ocorrências de relatório, não necessariamente 17 animes.
- Simulação da aplicação seguida de nova comparação: **0 alterações propostas**.
- Campos protegidos das **881 entradas anteriores** permaneceram iguais nessa simulação.

Os arquivos pessoais usados nessa comparação não estão no pacote.

## Interface e distribuição

A janela Tkinter foi instanciada sem exibição; os controles foram montados e Aplicar começou desabilitado. Também foi exercitado o fluxo da janela oculta: clicar em Conectar (abertura do Chrome simulada), entregar dois acessos fictícios por HTTP real, fechar a ponte, liberar Gerar prévia e limpar os acessos ao fechar a janela. Os módulos Python foram compilados e a ajuda da linha de comando foi executada. O ZIP foi conferido quanto à integridade e contém fontes, instruções, mapeamentos e testes, sem credenciais ou backups pessoais.

## Limite desta validação

Esta versão Python não executou uma nova sincronização autenticada nas suas contas durante os testes. O acesso HTTP autenticado e a compatibilidade atual das APIs serão conferidos quando você fornecer os acessos no programa. As operações de gravação foram testadas com respostas simuladas.
