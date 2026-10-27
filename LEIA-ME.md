# Crunchyroll → AniList — Python 1.5

**Login simplificado:** colar/digitar acesso fica dentro de **Login via token**. Depois de conectar, os controles de login são ocultados e aparecem os cartões das contas com **Trocar conta**. Veja **ATUALIZACAO_1_5.md**.

**Novo:** cartões com nicks e avatares das contas, seleção de itens, edição de alvo e exclusão local do plano. É possível aplicar por lotes e continuar com o restante na mesma prévia. Veja **ATUALIZACAO_1_4.md**.

Programa local para atualizar o progresso e o status da sua lista usando o histórico completo do Crunchyroll, pelas APIs. Depois de fornecer os acessos e iniciar a operação, você pode continuar usando o computador: o programa não controla mouse, teclado ou abas.

**Usuário AniList e perfil Crunchyroll são detectados automaticamente pela sessão.** Você não precisa digitar os nomes. Eles aparecem em cartões com avatar quando disponível, sem campos editáveis. Os acessos são identificados ao conectar. Selecione no navegador o perfil Crunchyroll cujo histórico deseja usar. Veja **ATUALIZACAO_1_3.md**.

**Versão 1.2:** a comparação automática prioriza o ID da série contido nos links externos do Crunchyroll retornados pela API do AniList, junto com a conferência de temporada e episódios. A prévia e o CSV mostram a origem de cada vínculo. Veja **ATUALIZACAO_1_2.md**.

## Abrir no Windows

1. Extraia **todos os arquivos** do ZIP para uma pasta.
2. Abra **Iniciar.cmd**. Se a associação de Python estiver configurada, também pode abrir **iniciar.pyw**.
3. É necessário **Python 3.10 ou superior com Tkinter**, incluído no instalador padrão para Windows. O motor e a interface usam a biblioteca padrão. Pillow é opcional para avatares JPEG/WebP; **Ativar_avatares.cmd** permite instalar essa opção.

O arquivo principal é `sync_anilist.py`. A interface é `interface.py`. Após instalar a extensão, mantenha a pasta no lugar ou carregue a extensão novamente depois de movê-la.

## Conectar automaticamente pelo Chrome (novo)

Abra o programa e clique em **Instalar extensão (uma vez)**. No Chrome, ative o **Modo do desenvolvedor** em **chrome://extensions**, clique em **Carregar sem compactação** e selecione a pasta **extensao_chrome** do pacote. Use o mesmo perfil do Chrome em que suas contas estão conectadas.

Depois, basta clicar em **Conectar pelo Chrome**. A extensão abre duas abas de apoio em segundo plano e envia os acessos diretamente para a janela Python. Se um site pedir, faça login ou selecione no Crunchyroll o perfil cujo histórico deseja usar. Aguarde o recebimento dos acessos e clique em **Gerar prévia**. Nenhuma mudança na lista é aplicada ao conectar.

Veja **CONEXAO_CHROME.md** para o passo a passo e funcionamento da conexão local. Não precisa copiar tokens manualmente. O botão se transforma em **Cancelar conexão** enquanto aguarda; a conexão expira em 3 minutos e fecha após receber os dois acessos. Os acessos continuam só em memória.

## Fornecer os acessos manualmente (alternativa)

Na tela de login, clique em **Login via token** para abrir os botões **Colar acesso** e **Digitar token**. Essas opções ficam recolhidas por padrão e desaparecem quando as contas são conectadas.

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

Os acessos ficam em memória e não são gravados nos backups, relatórios ou mapeamentos. Ao fechar o programa, é necessário fornecê-los novamente. O programa não solicita senha nem lê o banco de senhas/cookies do Chrome.

## Sincronizar

1. Com os acessos carregados, confira os nicks detectados nos cartões e clique em **Gerar prévia**.
2. Confira **Revisar plano** e **Pendências e itens ignorados**. Essa etapa só consulta as APIs.
3. Use as caixas **Aplicar** para escolher o lote. **Editar alvo** muda status/progresso; **Excluir do plano** retira linhas localmente. **Restaurar plano** desfaz a revisão local dos itens restantes.
4. Clique em **Aplicar marcados (N)** e confirme a conta e a quantidade.
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

Em HTTP 401/403, copie uma requisição nova. Se o perfil não puder ser conferido, confirme o perfil selecionado no Crunchyroll e conecte novamente. Se o site recusar clientes Python, é possível importar uma exportação completa do histórico e usar OAuth do AniList.

O Crunchyroll usa uma API interna do site, que pode mudar ou recusar requisições externas. A sessão web do AniList também depende do site; OAuth é a alternativa oficial. O programa interrompe quando encontra formato inesperado, paginação incompleta ou conta diferente. Não inclui renovação automática da sessão.

## Validação desta versão

Veja **VALIDACAO.md**. Foram usados testes automatizados e uma comparação offline com os dados já coletados. A aplicação Python não fez uma nova gravação autenticada nas suas contas durante essa validação.

Referências: [autenticação AniList](https://docs.anilist.co/guide/auth/), [limites da API](https://docs.anilist.co/guide/rate-limiting), [Network do Chrome](https://developer.chrome.com/docs/devtools/network/reference/).
