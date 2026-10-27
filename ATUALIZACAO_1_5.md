# Versão 1.5 — login recolhido

## Antes de conectar

A seção **Login** mostra **Conectar pelo Chrome** e **Login via token**.

Os botões **Colar acesso** e **Digitar token** de Crunchyroll/AniList ficam ocultos inicialmente. Clique em **Login via token** para abrir essas opções. Clique novamente para recolher.

Para importar um histórico JSON, escolha o arquivo na tela de login antes de fornecer o acesso AniList.

## Depois de conectar

Os controles de login, instalação da extensão e entrada manual ficam ocultos. Aparecem os cartões com nick/avatar das contas e uma opção **Trocar conta**, que retorna à tela de login e limpa os acessos da memória do programa.

Gerar prévia, revisar e aplicar lotes continuam disponíveis na área principal. Gerar outra prévia mantém os nicks visíveis e não reabre os controles de login.

Ao trocar de conta, a revisão atual é salva localmente e a seleção de histórico importado é limpa. As sessões abertas no Chrome não são encerradas.

Se a API recusar a sessão com HTTP 401/403, o programa volta à tela de login para permitir nova conexão.

## Atualizar

Feche o programa, substitua os arquivos pelos do ZIP 1.5 e abra **Iniciar.cmd**. A extensão continua compatível.

## Verificação

Foram exercitados os estados da interface com janela oculta e respostas simuladas: entrada manual fechada/aberta, conexão bem-sucedida, controles recolhidos, nicks preservados durante a prévia, troca de conta e login recusado permitindo nova tentativa.

O fluxo de avatares e três aplicações parciais simuladas também foi repetido com sucesso. O motor e as regras de sincronização não foram alterados nesta versão. Não houve novas gravações nas contas reais.
