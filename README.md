# AlmoxarifadoIA

Aplicacao em Python com `Streamlit` para consultar listas de pecas de almoxarifado usando a API do Gemini.

O usuario envia uma planilha `.xlsx` com os itens do estoque e depois pode fazer perguntas como:

- `Quais sensores tem no estoque?`
- `Qual a quantidade do item X?`
- `Quais itens estao em falta?`
- `Me faca um resumo do estoque`

## Requisitos

- Python 3.10 ou superior
- Conta com chave da API do Gemini

## Como baixar o projeto

Se estiver usando Git:

```powershell
git clone <URL_DO_REPOSITORIO>
cd ChatpyNovo
```

Se nao estiver usando Git:

1. Baixe os arquivos do projeto.
2. Extraia a pasta.
3. Abra o terminal dentro da pasta do projeto.

## Como criar o ambiente virtual

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativacao:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Como instalar as dependencias

Com a `venv` ativada:

```powershell
pip install -r requirements.txt
```

## Como configurar a chave da API

Crie um arquivo chamado `.env` na raiz do projeto com este conteudo:

```env
GEMINI_API_KEY=sua_chave_aqui
```

Voce tambem pode usar `GOOGLE_API_KEY`, mas o projeto hoje procura primeiro por `GEMINI_API_KEY`.

## Como executar a aplicacao

Com a `venv` ativada:

```powershell
streamlit run app.py
```

Depois disso, o Streamlit vai abrir no navegador ou mostrar no terminal a URL local, normalmente algo como:

```text
http://localhost:8501
```

## Como usar

1. Abra a tela de listas.
2. Clique em `Adicionar lista`.
3. Informe nome e descricao.
4. Envie uma planilha `.xlsx`.
5. Abra a consulta da lista cadastrada.
6. Faca perguntas no chat.

## Estrutura principal do projeto

- `app.py`: ponto de entrada da aplicacao
- `src/aplicacao.py`: inicializa a aplicacao e controla as telas
- `src/banco.py`: cria e acessa o banco SQLite
- `src/navegacao.py`: guarda o estado de navegacao no Streamlit
- `src/telas/`: telas da interface
- `src/servicos/`: regras de negocio e integracao com Gemini
- `src/utils/extracao_texto.py`: leitura do arquivo `.xlsx`
- `dados/`: banco SQLite gerado localmente
- `uploads/`: planilhas enviadas pelos usuarios

## Banco de dados

O projeto usa SQLite local.

O banco e criado automaticamente em:

```text
dados/almoxarifado_ia.db
```

Voce nao precisa criar esse arquivo manualmente.

## Observacoes importantes

- O projeto atualmente aceita apenas arquivos `.xlsx`.
- As pastas `dados/` e `uploads/` sao criadas automaticamente na primeira execucao.
- Se a API do Gemini retornar erro de quota (`429`), aguarde alguns segundos e tente novamente.

## Comandos uteis

Ativar a `venv`:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Rodar a aplicacao:

```powershell
streamlit run app.py
```
