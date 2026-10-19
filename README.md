# Project J.A.R.V.I.S.

> *"Just A Rather Very Intelligent System"* — Asistente de IA personal con HUD holográfico estilo Iron Man.

Aplicación full-stack de IA conversacional: frontend **Next.js 14 (App Router)** con un HUD animado, backend **FastAPI** con **LangChain + GPT-4o**, memoria vectorial sobre el repositorio de GitHub del usuario (**Pinecone + RAG**) y memoria a largo plazo relacional (**PostgreSQL**). Autenticación con **NextAuth.js** y efectos de sonido con **Howler.js**.

---

## 🏗️ Arquitectura

```
project-jarvis/
├── frontend/                  # Next.js 14 + TypeScript + Tailwind (HUD)
│   ├── app/
│   │   ├── layout.tsx         # Root layout + SessionProvider (NextAuth)
│   │   ├── page.tsx           # Pantalla principal del HUD
│   │   ├── globals.css        # Tailwind + utilidades sci-fi (hud-panel, glow...)
│   │   ├── api/auth/[...nextauth]/   # Route handler de NextAuth (GitHub OAuth)
│   │   └── components/
│   │       ├── hud/           # Overlays del HUD (radar, stats, scanlines)
│   │       ├── core/          # Núcleo SVG de la IA (Arc Reactor animado)
│   │       ├── chat/          # Panel de chat con J.A.R.V.I.S.
│   │       └── ui/            # Botones, paneles, inputs reutilizables
│   ├── lib/
│   │   ├── auth/              # Session provider de NextAuth
│   │   ├── voice/             # Comandos de voz (Web Speech API)
│   │   ├── sound/             # Sistema de sonido (Howler.js)
│   │   └── utils/             # Helpers (cn, formatters...)
│   └── public/sounds/         # Efectos de audio del HUD
├── backend/                   # FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── main.py            # Entry point, CORS, routers
│   │   ├── routers/           # github.py · ai.py · memory.py
│   │   ├── services/          # github_service · rag_service · agent_service · memory_service
│   │   ├── models/            # Modelos ORM (SQLAlchemy)
│   │   └── core/              # config.py (pydantic-settings) · database.py (async engine)
│   └── requirements.txt
├── scripts/
│   ├── ingest_repo.py         # Vectoriza el repo de GitHub → Pinecone
│   └── setup_db.py            # Inicializa las tablas de PostgreSQL
└── .env.example               # Plantilla de todas las variables de entorno
```

### Flujo de datos

1. El usuario habla o escribe en el HUD (frontend).
2. Next.js llama a `POST /api/ai/chat` en FastAPI.
3. `RAGService` recupera fragmentos relevantes del repo desde **Pinecone**.
4. `AgentService` (LangChain + **GPT-4o**) genera la respuesta con ese contexto.
5. `MemoryService` persiste la conversación y recuerdos en **PostgreSQL**.

---

## 🚀 Instalación y Setup

### Requisitos

- Node.js ≥ 18.17
- Python ≥ 3.11
- PostgreSQL ≥ 14 (local o gestionado: Neon, Supabase, RDS)
- Cuenta de OpenAI (API key con acceso a GPT-4o)
- Cuenta de Pinecone (índice serverless, dimensión 1536 para `text-embedding-3-small`)
- GitHub Personal Access Token (scope `repo`, lectura)

### 1. Variables de entorno

```bash
cp .env.example frontend/.env.local
cp .env.example backend/.env
# Edita ambos archivos con tus claves reales
```

Genera el secreto de NextAuth:

```bash
openssl rand -base64 32   # pégalo en NEXTAUTH_SECRET
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Inicializar base de datos relacional
python ../scripts/setup_db.py

# Vectorizar el repositorio de GitHub en Pinecone (una vez, o al actualizar)
python ../scripts/ingest_repo.py --dry-run   # prueba sin subir
python ../scripts/ingest_repo.py             # ingesta real

# Levantar la API (http://localhost:8000, docs en /docs)
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend (Next.js)

```bash
cd frontend
npm install          # o pnpm install / yarn
npm run dev          # http://localhost:3000
```

Coloca los efectos de sonido en `frontend/public/sounds/` (ej.: `boot.mp3`, `hover.mp3`, `response.mp3`).

### 4. Verificación

| Servicio | URL | Esperado |
|---|---|---|
| Frontend | http://localhost:3000 | HUD de J.A.R.V.I.S. |
| Backend | http://localhost:8000/health | `{"status":"ok"}` |
| Docs API | http://localhost:8000/docs | Swagger UI |

---

## 🔐 Variables de entorno (.env.example)

| Variable | Descripción |
|---|---|
| `OPENAI_API_KEY` | Clave de API de OpenAI (GPT-4o + embeddings) |
| `OPENAI_MODEL` | Modelo de chat (por defecto `gpt-4o`) |
| `OPENAI_EMBEDDING_MODEL` | Modelo de embeddings (`text-embedding-3-small`) |
| `PINECONE_API_KEY` | API key de Pinecone |
| `PINECONE_ENVIRONMENT` | Región/hosting del proyecto Pinecone |
| `PINECONE_INDEX_NAME` | Nombre del índice vectorial |
| `GITHUB_TOKEN` | PAT de GitHub con acceso al repo |
| `GITHUB_REPO_OWNER` | Propietario del repo a vectorizar |
| `GITHUB_REPO_NAME` | Nombre del repo a vectorizar |
| `DATABASE_URL` | Cadena de conexión PostgreSQL (memoria a largo plazo) |
| `DATABASE_URL_ASYNC` | Variante asyncpg usada por SQLAlchemy |
| `NEXTAUTH_SECRET` | Secreto JWT de NextAuth |
| `NEXTAUTH_URL` | URL base del frontend (`http://localhost:3000`) |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | OAuth de GitHub para NextAuth |
| `NEXT_PUBLIC_API_URL` | URL del backend para el frontend |
| `CORS_ORIGINS` | Orígenes permitidos en FastAPI |

---

## 🎨 Tema Tailwind sci-fi

El archivo `frontend/tailwind.config.ts` define la paleta del HUD:

- **`jarvis`** — cian neón `#00e5ff` (color primario, brillos `shadow-glow-cyan`)
- **`void`** — negro espacial `#030b14` (fondos)
- **`abyss`** — azul profundo `#0a1e3f` (superficies y bordes)
- **`holo`** — violeta holográfico `#8b5cf6` (estado "pensando")
- **`system.ok` / `alert.critical`** — verde sistema / rojo alerta
- Animaciones: `pulse-glow`, `radar-sweep`, `flicker`, `scanline`, `spin-slow/reverse`
- Utilidades listas en `globals.css`: `.hud-panel`, `.hud-button`, `.hud-text`, `.text-glow`, `.hud-background`

---

## 🗺️ Roadmap de fases

- [x] **Fase 1 — Fundamentos**: estructura, dependencias, env, tema Tailwind, esqueleto FastAPI ✅
- [ ] **Fase 2 — HUD visual**: núcleo SVG (Arc Reactor), overlays con Framer Motion + GSAP
- [ ] **Fase 3 — Chat + IA**: panel de chat conectado a `/api/ai/chat`, streaming de respuestas
- [ ] **Fase 4 — Voz y sonido**: Web Speech API (STT/TTS) + Howler.js
- [ ] **Fase 5 — GitHub + RAG**: dashboard del repo, ingesta incremental, citas de código
- [ ] **Fase 6 — Memoria y Auth**: historial persistente, preferencias del usuario, NextAuth

---

## ⚡ Scripts útiles

```bash
python scripts/setup_db.py --drop    # Recrear la base de datos desde cero
python scripts/ingest_repo.py        # Re-vectorizar el repo tras cambios
cd frontend && npm run type-check    # Verificación de tipos TypeScript
```

---

*“A little party never killed nobody.” — J.A.R.V.I.S.*
