# Validação — 26/10/2026

Ambiente: Windows, Python 3.13.3. O código usa apenas a biblioteca padrão e declara compatibilidade com Python 3.10 ou superior; outras versões não foram executadas nesta validação.

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
