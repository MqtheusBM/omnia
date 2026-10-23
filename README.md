# OmnIA

Sistema de **corреição judiciária inteligente** desenvolvido para apoiar corregedorias e tribunais na auditoria automatizada de processos judiciais com base em regras configuráveis.

---

## 🏛️ Contexto do Projeto

O **OmnIA** foi criado para modernizar o fluxo de correição de varas judiciais. Ele automatiza a verificação de conformidade dos processos usando regras parametrizáveis (ex.: paralisa­ção acima do prazo, ausência de cumprimento de ordem judicial, inconsistência de classificação) e apresenta os resultados em uma interface visual para equipes de correição.

---

## 📁 Estrutura do Repositório

```
OmnIA/
├── frontend/
│   └── omnia/          # Aplicação Angular (SSR) — interface principal do sistema
└── backend/            # API FastAPI / Python — serviço de inteligência e triagem
```


---

## 🚀 Como Executar

### Pré-requisitos

| Ferramenta | Versão recomendada |
|---|---|
| Node.js | 20.x ou superior |
| npm | 11.x ou superior |
| Angular CLI | 22.x |

### Instalação e execução

```bash
# 1. Acesse o diretório do frontend
cd frontend/omnia

# 2. Instale as dependências
npm install

# 3. Inicie o servidor de desenvolvimento
npm start
# ou: npx ng serve
```
A aplicação ficará disponível em **http://localhost:4200**

### Executar com a API

Em outro terminal, configure as credenciais do backend em `backend/.env` e inicie
MongoDB e a API conforme as instruções de `backend/README.md`. O frontend local
usa `http://localhost:8000` por padrão; o backend permite chamadas de
`http://localhost:4200` e `http://127.0.0.1:4200`.

Na tela **Aprovação e execução**, selecione um PDF e escolha **Enviar e iniciar
análise**. A tela acompanha o processamento e exibe respostas e evidências. O
questionário atualmente enviado é `questionario-exemplo-v1`.

O planejamento também consulta `GET /v1/processos/catalogo` e `GET /v1/processos/regras`.
Ao iniciar a correição, envia a quantidade escolhida e os IDs dos PDFs para
`POST /v1/correicoes`; o lote cria um job por PDF e acompanha em
`/acompanhamento?correicao_id=<id>`. Quando todos terminam, o fluxo abre a aprovação
com os resultados dos jobs. A revisão individual recebe as respostas e evidências
reais; ao emitir parecer, o serviço frontend gera o relatório com esses dados.
A pasta `processos` é montada como leitura no backend pelo Docker Compose. O lote
aceita até 30 PDFs.

O catálogo de regras executáveis está em
`backend/app/questionarios/regras_correcionais_v1.json`. A seleção da unidade no
frontend ainda é demonstrativa, pois os PDFs não têm metadados de unidade; ela não
filtra o lote. O backend retorna evidências e respostas por regra, mas ainda não
fornece eventos de tramitação.

Para produção, atualize `apiUrl` em
`frontend/omnia/src/app/enviroment/environment.prod.ts` para a URL implantada da
API e configure `CORS_ORIGINS` no backend com a origem pública do frontend.

---

## 🗺️ Fluxo Principal da Aplicação

O sistema segue um fluxo linear de 5 etapas acessíveis pelo menu lateral:

```
[01] Dashboard Correicional
     └── Visão geral de ocorrências, riscos e histórico de correições

[02] Planejamento
     └── Definição do universo de auditoria (classes, assuntos, período)

[03] Regras de Correição
     └── Seleção e configuração das regras a serem verificadas

[04] Aprovação e Execução
     └── Revisão e autorização antes de disparar a análise

[05] Resultados e Riscos
     └── Visualização dos processos sinalizados e seus veredictos
```

---

## 🧩 Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Framework | Angular 22 (com SSR via `@angular/ssr`) |
| Linguagem | TypeScript 6 |
| Estilização | TailwindCSS 3 + CSS Variables (design tokens) |
| Ícones | Google Material Symbols Outlined |
| Fonte | IBM Plex Sans (interface) · Newsreader (display) |
| Testes unitários | Vitest |
| Formatador | Prettier |

---

## 👥 Para a Equipe

- O arquivo de dados mockados está em `frontend/omnia/src/app/mock-data/prototype-data.ts`. Toda lógica de integração com a API futura deve substituir as importações desse arquivo nos services.
- O design system usa **CSS Variables** definidas em `src/styles.scss`. Toda nova cor ou token deve ser adicionada lá.
- Consulte a documentação dentro de cada pasta para orientações específicas de cada camada:
  - `frontend/omnia/` → `FRONTEND.md`
  - `src/app/components/` → `COMPONENTS.md`
  - `src/app/service/` → `SERVICES.md`
  - `src/app/guard/` → `GUARDS.md`
  - `src/app/mock-data/` → `MOCK_DATA.md`
  - `src/app/enviroment/` → `ENVIRONMENT.md`

---

## 📌 Status do Projeto

> ⚠️ **Protótipo funcional** — dados são mockados.
