# Versão 1.4 — contas com avatar e revisão por lotes

## Contas conectadas

Ao receber os acessos pelo Chrome ou ao fornecer os dois acessos manualmente, o programa identifica as contas em segundo plano. Os cartões mostram:

- **AniList — destino:** nick, ID e avatar quando fornecido pela API.
- **Crunchyroll — origem:** nome do perfil ativo e avatar quando disponível; o ID aparece se o nome não puder ser obtido.

As imagens são buscadas nos servidores públicos dos serviços **sem enviar Cookie ou Authorization**. Sem imagem disponível, aparecem as iniciais AL/CR. Não são gravadas em arquivos.

PNG/GIF funcionam pelo Tkinter. Para JPEG, WebP e melhor ajuste circular, o programa usa **Pillow quando instalado**. Neste computador, Pillow estava disponível durante os testes. Se necessário, abra **Ativar_avatares.cmd** uma vez; ele instala/atualiza essa biblioteca opcional. O motor de sincronização continua funcionando sem ela.

## Revisar antes de aplicar

A aba **Revisar plano** agora tem caixas na coluna **Aplicar**.

- Clique na caixa para marcar/desmarcar uma linha.
- **Marcar todos / Desmarcar todos** mudam as caixas de todas as linhas.
- **Somente selecionados** marca apenas as linhas destacadas. Use Ctrl/Shift para destacar várias.
- **Editar alvo**, ou duplo clique no título, permite ajustar o status e o número de episódios.
- **Excluir do plano**, ou Delete, retira as linhas destacadas desta prévia.
- **Restaurar plano** desfaz edições/exclusões locais dos itens que ainda não foram concluídos em lotes.

Uma linha destacada serve para editar/excluir. **As caixas marcadas determinam o que será aplicado.** O botão informa a quantidade marcada.

Excluir aqui é uma operação local de revisão. O programa não envia uma exclusão de entrada para o AniList.

## Atualizar parcialmente

Marque apenas o que deseja e clique em **Aplicar marcados (N)**. Depois da confirmação, o programa aplica e verifica esse lote. Os demais itens continuam disponíveis na mesma prévia.

Também é possível reduzir o alvo proposto de um anime, dentro do progresso confirmado pelo histórico. Exemplo: a prévia propõe concluir no episódio 12, mas você escolhe aplicar só até o episódio 8 como Assistindo. Depois do lote, o programa deixa o restante até 12 na tabela, **desmarcado**, já usando 8 como progresso atual. Você decide se/quando marcar o restante.

A edição:
- não reduz o progresso atual;
- não ultrapassa o progresso confirmado pelo histórico;
- só permite Concluído com total conhecido e progresso igual a esse total;
- preserva notas, datas, repetições, privacidade e listas pessoais.

Itens que a API informar como já aplicados, concluídos ou com progresso maior continuam sendo preservados. Uma alteração externa na entrada pode exigir nova prévia.

## Arquivos da revisão

Os arquivos originais da prévia são mantidos. A revisão é salva automaticamente em:

| Arquivo | Uso |
| --- | --- |
| revisao.json | Estado da tabela, com itens restantes, marcações e revisões |
| plano-revisado.json | Plano aplicável contendo **somente os itens marcados** |
| alteracoes-revisadas.csv | Tabela restante com coluna Aplicar: Sim/Não |
| aplicacoes/PASTA/plano.json | Cópia exata de cada lote enviado |
| aplicacoes/PASTA/backup-aplicacao-….json | Cópia antes desse lote |
| aplicacoes/PASTA/diario-aplicacao.jsonl | Tentativas e confirmações do lote |
| aplicacoes/PASTA/verificacao.json | Conferência do lote |
| aplicacoes/PASTA/anilist-depois.json | Lista após o lote |

O arquivo **revisao.json não pode ser aplicado diretamente**. Para a CLI, use **plano-revisado.json**, que respeita as caixas marcadas.

As exclusões e edições valem para esta prévia. Gerar uma prévia nova refaz a comparação com a conta atual. Se uma aplicação falhar, confira o relatório do lote e gere outra prévia para continuar.

## Atualizar o programa

Feche a versão anterior, substitua os arquivos pelos do ZIP 1.4 e abra **Iniciar.cmd**. A extensão de conexão continua compatível.

## Validação

- **85 testes do motor passaram**, incluindo 22 novos casos para seleção, edição, exclusão local, exportação, lotes, progresso restante, imagens e validação das contas.
- A janela foi exercitada oculta com PNG/JPEG fictícios e APIs simuladas: identificação automática, dois avatares, marcação, edição, exclusão/restauração e **três lotes** consecutivos.
- Cada lote gerou sua própria pasta; campos pessoais foram preservados e itens não marcados não foram alterados.
- A regressão offline dos 2.823 registros anteriores manteve os mesmos 83 alvos conferidos e zero alterações na segunda comparação simulada.

Não houve nova gravação nas contas reais durante os testes desta versão.

Referências: [avatar AniList](https://docs.anilist.co/reference/object/user), [Pillow opcional](https://pillow.readthedocs.io/en/stable/installation/basic-installation.html).
