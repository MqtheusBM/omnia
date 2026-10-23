# Omnia Backend

Serviço de análise de processos judiciais com **Google Document AI** (OCR) e provedor LLM configurável (**OpenAI** ou **Gemini**).

> ⚠️ **Aviso**: Este sistema é apoio à triagem processual e exige revisão humana. Não substitui decisão jurídica.

---

## 🚀 Início Rápido

### Pré-requisitos

- Python 3.11+
- MongoDB (local ou via Docker)
- Credenciais Google Cloud (Document AI)
- Chave da API do provedor LLM selecionado

### 1. Configurar ambiente

```bash
# Clonar e entrar no diretório
cd omnia_backend

# Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/macOS

# Instalar dependências
pip install -e ".[dev]"

# Copiar e configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais
```

### 2. Configurar credenciais no `.env`

Preencha as seguintes variáveis obrigatórias:

| Variável | Descrição |
|---|---|
| `LLM_PROVIDER` | Provedor ativo: `openai` ou `gemini` (padrão: `openai`) |
| `OPENAI_API_KEY` | Chave da API OpenAI, necessária quando `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | Modelo OpenAI (padrão: `gpt-6.1-sol`) |
| `GEMINI_API_KEY` | Chave de API do Gemini, necessária quando `LLM_PROVIDER=gemini` |
| `GEMINI_MODEL` | Modelo Gemini (padrão: `gemini-3.8-flash`) |
| `GOOGLE_CLOUD_PROJECT` | ID do projeto GCP |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho local para o JSON da conta de serviço |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Conteúdo JSON como segredo para deploys sem arquivo local |
| `DOCUMENT_AI_PROCESSOR_ID` | ID do processador Enterprise Document OCR |
| `GCS_BUCKET_PROCESSOS` | Nome do bucket GCS (para produção) |
| `GCS_PROCESSOS_PREFIX` | Prefixo dos PDFs do acervo no bucket (padrão: `processos`) |
| `STORAGE_BACKEND` | `local` para desenvolvimento local ou `gcs` para usar o bucket |

Para alternar entre os provedores, altere `LLM_PROVIDER` no `.env`. O processo de OCR permanece no Google Document AI.

### 3. Iniciar MongoDB

```bash
# Via Docker
docker run -d --name omnia-mongo -p 27017:27017 mongo:7

# Ou via Docker Compose (inclui app + mongo)
docker compose up -d
```

### 4. Executar a aplicação

```bash
# Modo desenvolvimento
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

A API estará disponível em: http://localhost:8000

Com `STORAGE_BACKEND=gcs`, o catálogo de processos lista PDFs no prefixo
`GCS_PROCESSOS_PREFIX` do bucket privado. Os nomes precisam seguir o padrão
`processo-<20 dígitos>.pdf`. A conta de serviço configurada para o backend
precisa poder listar e ler os objetos do bucket.

Por padrão, a API aceita chamadas do frontend Angular em `http://localhost:4200`
e `http://127.0.0.1:4200`. Para outros domínios, configure `CORS_ORIGINS` no
`.env` como uma lista de origens separadas por vírgula (por exemplo,
`CORS_ORIGINS=https://omnia.exemplo.gov.br`).

Documentação interativa: http://localhost:8000/docs

---

## 📡 Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Healthcheck |
| `GET` | `/v1/processos/catalogo` | PDFs disponíveis no acervo local ou no prefixo configurado do GCS |
| `GET` | `/v1/processos/regras` | Regras habilitadas para análise |
| `POST` | `/v1/processos/analisar` | Enviar PDF para análise |
| `GET` | `/v1/processos/{job_id}` | Consultar status do job |
| `GET` | `/v1/processos/{job_id}/resultado` | Obter resultado final |
| `POST` | `/v1/correicoes` | Iniciar lote de até 30 PDFs do acervo |
| `GET` | `/v1/correicoes/{correicao_id}` | Acompanhar jobs de uma correição |
| `GET` | `/v1/correicoes` | Listar execuções recentes para o dashboard |

### Exemplo de uso

```bash
# Enviar PDF para análise
curl -X POST http://localhost:8000/v1/processos/analisar \
  -F "file=@processo.pdf" \
  -F "questionario_id=questionario-exemplo-v1"

# Consultar status
curl http://localhost:8000/v1/processos/{job_id}

# Obter resultado
curl http://localhost:8000/v1/processos/{job_id}/resultado
```

---

## 🧪 Testes

```bash
# Executar todos os testes unitários
pytest

# Com cobertura
pytest --cov=app --cov-report=term-missing

# Apenas testes específicos
pytest tests/test_validation_service.py -v
```

---

## 🐳 Docker

```bash
# Build e execução completa
docker compose up -d --build

# Ver logs
docker compose logs -f app

# Parar tudo
docker compose down
```

---

## 📁 Estrutura do Projeto

```
omnia_backend/
├── app/
│   ├── api/
│   │   ├── routes_processos.py    # Endpoints HTTP
│   │   └── dependencies.py        # Injeção de dependências
│   ├── core/
│   │   ├── config.py              # Configurações (pydantic-settings)
│   │   ├── logging.py             # Logging estruturado JSON
│   │   └── security.py            # Validação PDF, hashing, sanitização
│   ├── models/
│   │   ├── schemas.py             # Schemas Pydantic v2
│   │   └── database.py            # CRUD MongoDB
│   ├── services/
│   │   ├── document_ai_service.py # OCR com Document AI
│   │   ├── ocr_text_service.py    # Formatação de texto paginado
│   │   ├── gemini_service.py      # Integração com Gemini Flash
│   │   ├── validation_service.py  # Validação defensiva de respostas
│   │   ├── storage_service.py     # Armazenamento (local/GCS)
│   │   ├── questionario_service.py# Carregamento de questionários
│   │   └── process_analysis_service.py # Orquestrador do pipeline
│   ├── prompts/
│   │   └── triagem_processual_v1.md   # Prompt versionado
│   ├── questionarios/
│   │   └── exemplo_v1.json            # Questionário de exemplo
│   └── main.py                        # Entrypoint FastAPI
├── tests/
│   ├── test_ocr_text_service.py
│   ├── test_validation_service.py
│   ├── test_prompt_builder.py
│   └── test_api.py
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🔐 Segurança

- Credenciais **nunca** são commitadas (protegidas pelo `.gitignore`).
- Logs estruturados **não** contêm dados de documentos, evidências ou PII.
- PDFs protegidos por senha são rejeitados.
- Armazenamento de artefatos usa referências (paths), não blobs no banco.

---

## 📄 Licença

Uso interno — todos os direitos reservados.
