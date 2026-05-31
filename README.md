# ChatPy

Aplicacao em `Streamlit` para estudar provas de concurso com apoio de IA.

O projeto permite:
- cadastrar provas, gabaritos e materiais complementares
- consultar questoes e respostas diretamente pelos arquivos indexados
- conversar com a IA usando `Gemini` ou `Ollama`
- gerar explicacoes e simulados a partir do material cadastrado

## Requisitos

- `Python 3.11+`
- `pip`
- `Git`
- `Ollama` opcional, caso voce queira usar IA local

## Setup rapido

1. Clone o repositorio:

```bash
git clone https://github.com/maurilioes97/chatpy.git
cd chatpy
```

2. Crie e ative um ambiente virtual:

```bash
python -m venv venv
venv\Scripts\activate
```

3. Instale as dependencias:

```bash
pip install -r requirements.txt
```

4. Crie o arquivo `.env` a partir do exemplo:

```bash
copy .env.example .env
```

5. Ajuste as variaveis do `.env` conforme o provider que voce vai usar.

6. Rode a aplicacao:

```bash
streamlit run src/app.py
```

A aplicacao abre, por padrao, em `http://localhost:8501`.

## Variaveis de ambiente

Crie um arquivo `.env` na raiz do projeto. Use o arquivo `.env.example` como base.

Variaveis principais:

- `LLM_PROVIDER`: provider padrao. Valores esperados: `gemini` ou `ollama`
- `GEMINI_API_KEY`: chave da API Gemini
- `GEMINI_MODEL`: modelo Gemini usado pela aplicacao
- `OLLAMA_HOST`: URL do servico local do Ollama
- `OLLAMA_MODEL`: modelo Ollama que sera usado
- `OLLAMA_TIMEOUT`: timeout das requisicoes ao Ollama, em segundos
- `OLLAMA_NUM_CTX`: tamanho de contexto enviado ao Ollama
- `OLLAMA_MAX_DOCUMENT_CHARS`: limite de caracteres de anexos enviados ao Ollama
- `OLLAMA_MAX_DOCUMENT_SECTIONS`: numero maximo de excertos de anexos enviados ao Ollama
- `OLLAMA_MAX_HISTORY_MESSAGES`: quantidade de mensagens recentes usadas no contexto local
- `DIRECT_STUDY_RESOLVER_ENABLED`: ativa consultas diretas de questoes e gabaritos sem usar LLM
- `ADMIN_USERNAME`: nome de usuario que deve receber papel de admin

## Exemplo de `.env`

```env
LLM_PROVIDER=ollama

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:8b
OLLAMA_TIMEOUT=1200
OLLAMA_NUM_CTX=16384
OLLAMA_MAX_DOCUMENT_CHARS=16000
OLLAMA_MAX_DOCUMENT_SECTIONS=4
OLLAMA_MAX_HISTORY_MESSAGES=6

DIRECT_STUDY_RESOLVER_ENABLED=true

GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-latest

ADMIN_USERNAME=admin
```

## Usando com Gemini

1. Preencha `GEMINI_API_KEY` no `.env`
2. Defina:

```env
LLM_PROVIDER=gemini
```

3. Rode o app normalmente:

```bash
streamlit run src/app.py
```

## Usando com Ollama

1. Instale o Ollama
2. Baixe o modelo desejado:

```bash
ollama pull deepseek-r1:8b
```

3. Inicie o servico local do Ollama:

```bash
ollama serve
```

4. Configure o `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:8b
```

5. Rode o app:

```bash
streamlit run src/app.py
```

## Banco e arquivos

- O banco SQLite e criado automaticamente em `data/chatbot.db`
- Os arquivos enviados para provas e gabaritos ficam em `data/equipment_files/`
- O app inicializa o banco ao subir por meio de [src/app.py](C:/Users/Maurilio/ProjetosPy/maurilioeufrasio/chatpy/src/app.py)

## Executando com Docker

Build e subida com `docker compose`:

```bash
docker compose up --build
```

Depois disso, acesse:

```text
http://localhost:8501
```

Observacoes:
- o container usa `Dockerfile` e `docker-compose.yml` da raiz
- no `docker-compose.yml`, o `OLLAMA_HOST` aponta para `http://host.docker.internal:11434`
- se for usar `Ollama` junto com Docker, o servico do Ollama precisa estar acessivel na maquina host

## Estrutura principal

```text
src/
  app.py
  models/
  pages/
  services/
  utils/
data/
  chatbot.db
  equipment_files/
```

## Dicas

- Nao suba seu `.env` real para o GitHub
- Prefira manter um `.env.example` atualizado para onboarding
- Se mudar as variaveis suportadas pela aplicacao, atualize o README e o `.env.example` juntos
