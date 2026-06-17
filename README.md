# AlmoxarifadoIA

Aplicacao em Python com `Streamlit` para consultar listas de pecas de almoxarifado com apoio da API do Gemini.

O usuario cadastra uma planilha `.xlsx`, abre uma conversa para aquela lista e faz perguntas em linguagem natural, por exemplo:

- `Quais sensores estao disponiveis?`
- `Qual a quantidade do item X?`
- `Quais itens estao abaixo do minimo?`
- `Me faca um resumo do estoque`

## Tecnologias

- Python
- Streamlit
- SQLite
- Google Gemini API
- OpenPyXL

## Requisitos

- Python 3.10 ou superior
- Chave da API do Gemini

## Como baixar o projeto

Com Git:

```powershell
git clone <URL_DO_REPOSITORIO>
cd ChatpyNovo
```

Sem Git:

1. Baixe o projeto em `.zip`.
2. Extraia a pasta.
3. Abra o terminal dentro da pasta do projeto.

## Como criar e ativar a venv

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

## Como configurar a API do Gemini

Crie um arquivo `.env` na raiz do projeto:

```env
GEMINI_API_KEY=sua_chave_aqui
```

O projeto tambem aceita `GOOGLE_API_KEY`, mas procura primeiro por `GEMINI_API_KEY`.

## Como executar

Com a `venv` ativada:

```powershell
streamlit run app.py
```

Normalmente a aplicacao abre em:

```text
http://localhost:8501
```

## Fluxo de uso

1. Abra a pagina inicial.
2. Clique em Baixar planilha teste
3. Clique em `Entrar no sistema`.
4. Na tela de listas, clique em `Adicionar lista`.
5. Informe o nome, a descricao e envie a planilha teste`.xlsx`.
6. Abra a lista cadastrada.
7. Converse com o assistente sobre os itens da planilha.

## Telas da aplicacao

### 1. Pagina inicial

- Apresenta o sistema
- Mostra os integrantes do projeto
- Tem o botao `Entrar no sistema`
- Tem o botao `Baixar planilha teste`

### 2. Lista de listas

- Exibe as listas cadastradas
- Permite buscar por nome ou descricao
- Permite abrir ou excluir uma lista

### 3. Adicionar lista

- Recebe nome da lista
- Recebe descricao
- Aceita upload de arquivo `.xlsx`

### 4. Consulta de estoque

- Mostra a lista atual
- Mantem historico de conversas
- Permite criar nova conversa
- Permite excluir conversas
- Envia perguntas para o Gemini com base no conteudo da planilha

## Estrutura principal do projeto

- `app.py`: ponto de entrada
- `src/aplicacao.py`: inicializacao e roteamento das telas
- `src/configuracoes.py`: configuracoes gerais do projeto
- `src/banco.py`: criacao e acesso ao banco SQLite
- `src/navegacao.py`: controle de tela e estado atual
- `src/telas/`: interface Streamlit
- `src/servicos/`: cadastro de listas, conversas e integracao com Gemini
- `src/utils/extracao_texto.py`: leitura do arquivo `.xlsx`
- `dados/`: banco local gerado automaticamente
- `uploads/`: arquivos enviados

## Banco de dados

O projeto usa SQLite local e cria automaticamente o arquivo:

```text
dados/almoxarifado_ia.db
```

Nao e necessario criar esse arquivo manualmente.

## Configuracoes atuais

- Modelo Gemini usado: `gemini-3.5-flash`
- Formato aceito no upload: `.xlsx`
- Arquivos enviados sao salvos localmente na pasta `uploads/`

## Observacoes importantes

- A aplicacao hoje foi pensada para trabalhar com planilhas `.xlsx`.
- O conteudo da planilha e extraido e enviado ao assistente como texto.
- As pastas `dados/` e `uploads/` sao criadas automaticamente na primeira execucao.
- Em caso de erro temporario da API do Gemini, o chat mostra uma mensagem resumida com o codigo do erro.
- Se a conta estiver sem quota, podem ocorrer erros como `429`.

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
