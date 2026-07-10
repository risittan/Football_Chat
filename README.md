# ⚽ FootballGPT — AI Football Chatbot with Persistent Memory

A football-focused conversational AI built with Flask, powered by a local **Ollama** LLM and a **three-agent architecture** that supports real-time data fetching, semantic memory, and multi-turn conversation.

---

## ✨ Features

- 🧠 **Persistent Vector Memory** — Remembers user preferences (favourite teams, players, opinions) across sessions using ChromaDB and semantic embeddings
- 🔴 **Live Football Data** — Fetches real-time scores, fixtures, standings, player stats, and top scorers via [API-Football](https://www.api-football.com/)
- 🛠️ **Tool Calling** — LLM autonomously decides when to call external tools (no hardcoded triggers)
- 💬 **Multi-turn Conversations** — Per-session conversation history with a `/api/reset` endpoint
- ⚡ **Parallel Agent Execution** — Memory extraction runs concurrently with response generation for zero added latency
- 🔍 **Deduplication** — Cosine similarity check prevents storing duplicate memories

---

## 🏗️ Architecture

The system uses three cooperative agents running per request:

```
User Message
     │
     ├──► Agent 3 (Memory Retrieval) ──► Semantic search in ChromaDB
     │         │                              │
     │         └──────────────────────────────┘
     │                                        │
     ├──► Agent 1 (Chat + Tool Calling) ◄─────┘
     │         │
     │         ├── Tool call? ──► API-Football ──► Second LLM call ──► Reply
     │         └── No tool?   ──────────────────────────────────────► Reply
     │
     └──► Agent 2 (Memory Extraction) ── runs in parallel, stores to ChromaDB
```

| Agent | Role |
|---|---|
| **Agent 1** | Main chat agent — answers questions, calls tools when needed |
| **Agent 2** | Silently extracts and stores memorable facts from user messages |
| **Agent 3** | Retrieves relevant memories before each response |

---

## 🧰 Tech Stack

| Component | Technology |
|---|---|
| Backend | Python / Flask |
| LLM | [Ollama](https://ollama.ai) — `rafw007/qwen35-claude-coder:4b` |
| Embeddings | [OpenRouter](https://openrouter.ai) — `qwen/qwen3-embedding-4b` |
| Vector Store | [ChromaDB](https://www.trychroma.com/) (persistent, local) |
| Football Data | [API-Football v3](https://www.api-football.com/) |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally
- An [OpenRouter](https://openrouter.ai) API key (for embeddings)
- An [API-Football](https://www.api-football.com/) API key (for live data)

### 1. Clone the repository

```bash
git clone https://github.com/risittan/chat_embeddings.git
cd chat_embeddings
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Pull the Ollama model

```bash
ollama pull rafw007/qwen35-claude-coder:4b
```

### 4. Configure environment variables

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
Embedding_API_KEY=your_openrouter_api_key_here
FOOTBALL_API_KEY=your_api_football_key_here
```

### 5. Run the app

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Chat UI |
| `POST` | `/api/chat` | Send a message |
| `POST` | `/api/reset` | Clear a session's conversation history |
| `GET` | `/api/memories` | View all stored memories |

### `/api/chat` request body

```json
{
  "message": "Who is top of the Premier League?",
  "session_id": "user-123"
}
```

---

## 🛠️ Available Tools

The LLM automatically selects the appropriate tool based on the user's query:

| Tool | Description |
|---|---|
| `get_standings` | League table / standings |
| `get_fixtures` | Today's matches or a team's schedule |
| `get_live_scores` | Currently live scores |
| `get_player_stats` | Goals, assists, cards, rating for a player |
| `get_top_scorers` | Golden Boot leaderboard for a league |

---

## 🗂️ Project Structure

```
chat_embeddings/
├── app.py              # Main Flask application + all agents
├── requirements.txt    # Python dependencies
├── .env                # Your secret keys (never commit this)
├── .env.example        # Template for environment variables
├── .gitignore
├── chroma_db/          # Persistent ChromaDB vector store (auto-created)
├── static/             # CSS / JS assets
└── templates/
    └── index.html      # Chat UI
```

---

## ⚠️ Notes

- The `chroma_db/` directory is created automatically on first run and persists memory between restarts.
- The Football API has a free tier with rate limits — check your plan at [api-football.com](https://www.api-football.com/).
- Ollama must be running locally (`ollama serve`) before starting the app.

---

## 📄 License

MIT
