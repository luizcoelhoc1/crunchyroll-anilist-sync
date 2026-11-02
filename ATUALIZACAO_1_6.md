# Versão 1.6.2 — instalador Windows e correção do arrasto

## Instalar

Baixe `CrunchyrollAniListSync-1.6.2-x64.msi` na [release v1.6.2](https://github.com/luizcoelhoc1/crunchyroll-anilist-sync/releases/tag/v1.6.2), execute o instalador e abra **Crunchyroll - AniList Sync** pelo menu Iniciar. Python, Tkinter e Pillow estão incluídos.

O `.env` opcional, os logs e os relatórios da versão instalada ficam em `%LOCALAPPDATA%\CrunchyrollAniListSync`. O modelo `.env.example` acompanha o programa. Confira o [guia de uso](LEIA-ME.md) para configurar as contas.

## Novidades desde a versão 1.5

- Instalador MSI por usuário para Windows x64, com dependências incluídas e atalho no menu Iniciar.
- Interface escura com menus próprios, barra de título integrada e contas na lateral.
- Correção do encerramento fatal ao arrastar a janela, preservando o movimento nativo do Windows.
- Autorização AniList no navegador habitual e login direto Crunchyroll com escolha de perfil e sessões protegidas no Windows.
- Revisão de progresso e comentário opcional para atualizações de exatamente um episódio.
- `task compile` incrementa automaticamente a versão de correção; registra a nova versão somente após compilar e verificar com sucesso.

## Validação

237 testes Python e 6 testes JavaScript passaram. O MSI foi conferido e o executável abriu, recebeu movimento da janela e fechou com dados temporários vazios. Os testes não instalaram o MSI nem realizaram sincronizações autenticadas nas contas reais.
