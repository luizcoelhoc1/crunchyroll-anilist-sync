# Crunchyroll → AniList Sync

Aplicativo Python para comparar o histórico do Crunchyroll com sua lista do AniList e aplicar atualizações revisadas.

**Versão 1.5.** [Baixar esta versão](https://github.com/luizcoelhoc1/crunchyroll-anilist-sync/releases/tag/v1.5) · [Instruções completas](LEIA-ME.md) · [Conectar pelo Chrome](CONEXAO_CHROME.md)

## Usar no Windows

1. Baixe e extraia o ZIP da versão desejada.
2. Instale Python 3.10 ou superior com Tkinter.
3. Abra **Iniciar.cmd**.
4. Carregue uma vez a pasta **extensao_chrome** em `chrome://extensions`, pelo modo do desenvolvedor.
5. Clique em **Conectar pelo Chrome**, confira as contas e gere uma prévia.
6. Revise, selecione os itens e aplique o lote desejado.

Pillow é opcional para melhorar o suporte aos avatares; **Ativar_avatares.cmd** instala essa dependência.

## Recursos

- Coleta paginada pela API, sem rolar o histórico na tela.
- Conexão com sessões já abertas no Chrome, sem armazenar acessos em disco.
- Identificação de contas, nicks e avatares.
- Correspondência por mapeamentos conferidos e IDs dos links Crunchyroll, com verificação de temporada e parte.
- Prévia com marcação, edição de progresso e exclusão local de itens do plano.
- Aplicação parcial, backups, diário de operações e verificação final.
- Preservação de notas, observações, privacidade, datas e progresso maior.

## Desenvolvimento

```sh
python -m unittest discover -s tests -v
node --test tests/test_extension.mjs
```

Node.js é necessário apenas para os testes da extensão. Veja [VALIDACAO.md](VALIDACAO.md) para os testes realizados e seus limites.

## Versões e dados locais

O histórico Git começa no pacote completo preservado da **1.4**, que já reúne os recursos anteriores. A **1.5** tem seu próprio commit e tag. As notas das versões 1.2 e 1.3 documentam a evolução anterior; não existem snapshots completos preservados dessas versões neste repositório.

O repositório contém código, testes, documentação e regras de catálogo. Não inclui tokens, cookies, exportações do histórico nem backups da lista. O arquivo `mapeamentos_lumimao.json` contém IDs públicos e regras de episódios usadas pelo aplicativo.

Crunchyroll usa uma API interna sujeita a mudanças. Gere e confira a prévia antes de aplicar alterações.
