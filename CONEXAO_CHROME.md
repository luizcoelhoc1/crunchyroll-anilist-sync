# Conectar pelo Chrome — instalação única

1. Extraia o ZIP inteiro para uma pasta fixa.
2. Abra **Iniciar.cmd**.
3. Clique em **Instalar extensão (uma vez)**. O programa abre a pasta da extensão e a página de extensões do Chrome.
4. No Chrome, em **chrome://extensions**, ative **Modo do desenvolvedor**.
5. Clique em **Carregar sem compactação** e selecione a pasta **extensao_chrome** que veio no ZIP.
6. Confira que a extensão **Crunchyroll → AniList — conexão local** ficou ativada.

Instale no mesmo perfil do Chrome em que você já usa Crunchyroll e AniList. Mantenha a pasta no lugar; o Chrome carrega a extensão a partir dela.

## Nas próximas vezes

1. Abra o programa e clique em **Conectar pelo Chrome**.
2. O Chrome abre uma página local de conexão. A extensão abre duas abas de apoio **em segundo plano**, sem alterar suas abas existentes.
3. Se algum site pedir, faça login ou selecione na aba do Crunchyroll o perfil cujo histórico deseja usar. Se já estiver conectado, isso pode não ser necessário.
4. Aguarde **Acessos entregues ao programa**. As abas de apoio são fechadas quando ainda estão nas páginas de coleta.
5. Volte ao programa e clique em **Gerar prévia**. Os nomes do AniList e do perfil Crunchyroll são detectados automaticamente. Confira as contas e as mudanças antes de **Aplicar alterações**.

Você pode continuar usando o PC durante as consultas. Não precisa abrir F12 ou copiar tokens. A conexão não aplica mudanças na lista.

## Se a página ficar aguardando

- Confirme que a extensão está ativada **nesse perfil do Chrome**.
- Se instalou enquanto a página já estava aberta, recarregue a página local.
- A conexão vale por **3 minutos**. Se expirar, clique novamente em **Conectar pelo Chrome**.
- Veja as abas de apoio: o Crunchyroll pode estar aguardando login ou escolha de perfil; o AniList pode pedir login.
- Use uma janela normal do Chrome. A extensão não é configurada para navegação anônima.
- Se o Chrome abrir a página em outro perfil, abra o endereço da página local no perfil em que instalou a extensão.
- O programa ainda oferece **Colar acesso**, **Digitar token** e importação do histórico como alternativas.

## Como funciona

A extensão observa somente as requisições de histórico do Crunchyroll e GraphQL do AniList, nas abas de apoio criadas para a conexão ativa. Entrega os headers necessários ao processo Python por uma conexão temporária em **127.0.0.1**, autenticada por uma chave aleatória por clique. A chave expira; o servidor fecha quando recebe os dois acessos, ao cancelar ou ao fechar o programa.

As credenciais não são gravadas em arquivos ou no armazenamento da extensão. A extensão guarda apenas a configuração temporária da conexão e os indicadores de recebimento em **storage.session**, mantido na memória do Chrome. Não acessa o banco de senhas ou arquivos de cookies do navegador.

Permissões: **webRequest**, **storage** e acesso somente a **www.crunchyroll.com**, **anilist.co** e **127.0.0.1**. Não pede acesso a todos os sites, debugger ou modo de depuração remota. O botão **Conectar** não instala a extensão automaticamente; a instalação ocorre pelos controles normais do Chrome.

Ao fechar a página local antes de terminar, a conexão permanece ativa até o cancelamento no programa ou o prazo de 3 minutos. Ao concluir, você já pode fechar a página local.

Referências oficiais: [carregar extensão local no Chrome](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked), [webRequest](https://developer.chrome.com/docs/extensions/reference/api/webRequest), [requisições de rede das extensões](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests), [storage.session](https://developer.chrome.com/docs/extensions/reference/api/storage).
