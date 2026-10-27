# Versão 1.3 — contas e perfil detectados automaticamente

Não é necessário digitar o usuário do AniList ou o nome do perfil Crunchyroll.

- **AniList:** o programa consulta **Viewer { id name }** com a sessão/token fornecido. A API identifica a conta autenticada.
- **Crunchyroll:** usa **profile_id** da sessão ativa e consulta a lista de perfis para obter o nome correspondente. Não escolhe o primeiro perfil, o perfil principal ou um nome fixo.
- Os dois nomes aparecem como **informações somente para leitura** durante a geração da prévia. A confirmação antes de aplicar mostra o AniList de destino e o perfil de origem.
- Se a consulta do nome Crunchyroll não estiver disponível, o programa mostra o **ID do perfil**. A coleta do histórico ainda precisa ser aceita pela API com o mesmo acesso.
- Se o token não informar qual é o perfil ativo, a execução para e solicita uma nova conexão; não adivinha outro perfil.
- Ao importar um histórico JSON, a origem aparece como **Histórico importado**, sem afirmar que é o perfil ativo do navegador.

Selecione no site do Crunchyroll o perfil cujo histórico deseja usar **antes de conectar**. Essa seleção continua sendo feita no navegador; o programa detecta o perfil da sessão capturada.

## Usar

1. Abra **Iniciar.cmd**.
2. Clique em **Conectar pelo Chrome**.
3. Clique em **Gerar prévia**.
4. Confira os nomes detectados e as alterações antes de aplicar.

O protocolo da extensão continua compatível com as versões anteriores. Os textos de orientação foram atualizados para não exigir um perfil com nome fixo. Não é necessário instalar a extensão de novo para usar a detecção automática.

## Linha de comando

Sem **--user** e **--profile**, a identidade é detectada. Esses parâmetros continuam disponíveis como verificações opcionais de uma conta/perfil esperados, para quem quiser usá-los em scripts.

## Validação

**63 testes do motor passaram:** 35 existentes, 18 de correspondência por links e 10 de identificação automática. Foram testados o Viewer autenticado, o perfil ativo fora da primeira posição, nomes diferentes dos antigos padrões, nome de perfil indisponível, ausência de ID de perfil e a preservação das verificações opcionais.

A janela foi exercitada oculta com APIs simuladas, tanto para coleta online como para importação JSON: exibe a identidade detectada, mantém os campos somente para leitura e conserva o plano após preencher os nomes.

A regressão offline dos 2.823 registros anteriores continuou produzindo os mesmos 83 alvos conferidos, com zero alterações adicionais na segunda comparação simulada. Não houve nova gravação nas contas durante esta atualização.

Referência: [Viewer do AniList](https://docs.anilist.co/guide/graphql/queries/user).
