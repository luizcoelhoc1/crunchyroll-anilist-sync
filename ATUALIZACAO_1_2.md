# Versão 1.2 — correspondência pelos links do Crunchyroll

O programa passou a usar os links retornados pelo campo **externalLinks** da API do AniList para priorizar candidatos da mesma série Crunchyroll.

## Ordem da comparação

1. Mantém os **mapeamentos já conferidos** do seu histórico, incluindo divisões em partes e especiais.
2. Nos grupos sem mapeamento, extrai o **ID da série Crunchyroll** do histórico e dos links do AniList. Idioma da URL, nome no endereço e parâmetros não alteram esse ID.
3. Prioriza os candidatos com o mesmo ID e confere **temporada, parte, formato e numeração**.
4. Quando a franquia está confirmada pelo ID, um rótulo explícito de temporada permite diferenças de tradução no nome base.
5. Se não houver link utilizável, mantém a alternativa de **título exato e único**, com as mesmas conferências.
6. Nome igual com um link apontando explicitamente para outra série é uma contradição e fica pendente. Links compartilhados entre candidatos indistinguíveis também ficam pendentes.

O link da série sozinho não escolhe uma temporada, parte ou especial. Um catálogo parcial contendo apenas uma segunda parte não faz essa parte virar a temporada inteira. Partes em algarismos romanos, como **Part II**, também são consideradas.

## Busca por API

A pesquisa por nome continua ajudando a descobrir candidatos na API. Depois, o ID contido no link é usado como evidência principal para a seleção automática. A consulta também coleta uma rodada de **prequelas e sequelas** dos resultados, para não depender apenas das primeiras posições da pesquisa.

Não é feita uma varredura completa do catálogo do AniList, nem são abertas as URLs externas. Os links são interpretados localmente.

## Conferir o motivo do vínculo

A tabela da prévia e o CSV agora têm a coluna **Correspondência**:

- **Mapeamento:** regra já conferida no arquivo de mapeamentos.
- **ID Crunchyroll:** ID do link externo confirmado, junto com a temporada.
- **Titulo:** alternativa por nome, sem evidência de link utilizável.
- **Plano anterior:** relatório criado por uma versão anterior, sem esse campo.

O **plano.json** inclui os detalhes em **matches**: método, grupo de origem e, quando disponível, ID e URL da série. Assim você pode conferir a evidência utilizada.

## Atualizar

Feche o programa antes de substituir os arquivos. Extraia o ZIP atualizado e abra **Iniciar.cmd** novamente. O botão de conexão e o protocolo da ponte continuam iguais aos da versão 1.1; a extensão não mudou.

Se mantiver a extensão instalada a partir de outra pasta, mantenha essa pasta no lugar. Se mover a pasta da extensão, carregue-a novamente no Chrome, conforme **CONEXAO_CHROME.md**.

## Validação

Passaram os **35 testes existentes do motor** e **18 novos testes** de links, temporadas, partes, evidências e consulta de obras relacionadas. A comparação offline com os **2.823 registros** do histórico anterior manteve exatamente os **83 alvos** conferidos; uma segunda comparação simulada propôs **0 alterações**. A nova coluna também foi verificada na janela Tkinter oculta e no CSV.

Esta atualização não aplicou mudanças nas suas contas. Veja **VALIDACAO.md** para o escopo dos testes.

Referências da API: [externalLinks](https://docs.anilist.co/reference/object/media), [consulta de catálogo](https://docs.anilist.co/reference/query).
