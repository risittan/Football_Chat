from flask import Flask, request, jsonify, render_template
import requests
import json
from datetime import datetime
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import os
import uuid
import chromadb

# Load environment variables from .env file
load_dotenv()
EMBEDDING_API_KEY = os.getenv("Embedding_API_KEY")
FOOTBALL_API_KEY  = os.getenv("FOOTBALL_API_KEY")

app = Flask(__name__)

# ─── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "rafw007/qwen35-claude-coder:4b"

SYSTEM_PROMPT = """You are FootballGPT — a passionate, knowledgeable football (soccer) expert and conversationalist.
You live and breathe the beautiful game.

You can discuss:
- Match results, fixtures, and standings
- Player stats, transfers, and career histories
- Club histories, trophies, and rivalries
- Tactics, formations, and coaching philosophies
- World Cup, Champions League, Premier League, La Liga, Bundesliga, Serie A, and all major competitions
- Football legends and rising stars
- VAR controversies, offside debates, and refereeing decisions
- Fantasy football tips
- Stadium history, atmosphere, and fan culture

Personality:
- Enthusiastic and engaging — you LOVE talking football
- Use football terminology naturally (e.g., "clean sheet", "brace", "nutmeg", "tiki-taka")
- Drop in fun stats and trivia when relevant
- If the user asks something off-topic (not football-related), politely redirect them back to football

IMPORTANT: When the user asks about current standings, live scores, fixtures, player stats,
or recent results, you MUST use the available tools to fetch real data. Never guess or make up football data.

Common player IDs: Salah=306, Haaland=1100, Kane=184, Mbappe=278, Ronaldo=874, Messi=154
Common team IDs: Arsenal=42, Liverpool=40, Man City=50, Man Utd=33, Tottenham=47, Chelsea=49
Common league IDs: Premier League=39, La Liga=140, Bundesliga=78, Serie A=135, Ligue 1=61, Champions League=2
Current season: 2024 (the 2024/25 season — use this as default unless user specifies otherwise)

Keep your answers informative but conversational. Use emojis sparingly for flair ⚽🏆."""

MEMORY_SYSTEM_PROMPT = """You are a memory extraction agent. Your job is to extract any
important personal information worth remembering about the user
from their message. This includes preferences, favourite teams,
favourite players, opinions, and personal facts.

Respond ONLY in this exact JSON format:
{"imp": "description of what to remember, or null if nothing worth storing"}

If there is nothing worth storing, return: {"imp": null}
Output ONLY the JSON, nothing else."""

# Per-session conversation history
conversation_store: dict[str, list] = {}

# ─── ChromaDB setup ───────────────────────────────────────────────────────────
chroma_client     = chromadb.PersistentClient(path="./chroma_db")
memory_collection = chroma_client.get_or_create_collection(
    name="football_gpt_memories",
    metadata={"hnsw:space": "cosine"},
)
print(f"[ChromaDB] Loaded — {memory_collection.count()} memories in store")

# ─── API-Football config ──────────────────────────────────────────────────────
FOOTBALL_HEADERS = {"x-apisports-key": FOOTBALL_API_KEY, "Accept": "application/json"}
FOOTBALL_BASE    = "https://v3.football.api-sports.io"

# ─── Tool definitions ─────────────────────────────────────────────────────────
TOOLS = [






    
    {

        "type": "function",
        "function": {
            "name": "get_standings",
            "description": "Get current league standings/table. Use for questions about league position, points, who is top, relegation battle etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "league_id": {"type": "integer", "description": "League ID: 39=Premier League, 140=La Liga, 78=Bundesliga, 135=Serie A, 61=Ligue 1, 2=Champions League"},
                    "season":    {"type": "integer", "description": "Season year e.g. 2025 for 2025/26 season"}
                },
                "required": ["league_id", "season"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fixtures",
            "description": "Get football fixtures — today's matches, or full season fixtures for a specific team. Use for questions about today's games, a team's schedule, or recent results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "league_id": {"type": "integer", "description": "League ID: 39=Premier League, 140=La Liga, 78=Bundesliga, 135=Serie A, 61=Ligue 1"},
                    "season":    {"type": "integer", "description": "Season year e.g. 2025. Required if filtering by team."},
                    "team_id":   {"type": "integer", "description": "Team ID to get their fixtures: Arsenal=42, Liverpool=40, Man City=50, Man Utd=33, Tottenham=47, Chelsea=49"},
                    "today":     {"type": "boolean", "description": "Set true to get only today's fixtures"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_scores",
            "description": "Get currently live football scores. Use when user asks about games happening right now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "league_id": {"type": "integer", "description": "Optional league ID to filter"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_stats",
            "description": "Get detailed stats for a specific player — goals, assists, appearances, cards etc. Use for questions about a player's performance or stats this season.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "integer", "description": "Player ID: Salah=306, Haaland=1100, Kane=184, Mbappe=278, Ronaldo=874, Messi=154, Saka=1403, Rashford=1446"},
                    "season":    {"type": "integer", "description": "Season year e.g. 2025 for 2025/26 season"}
                },
                "required": ["player_id", "season"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_scorers",
            "description": "Get top scorers for a league in a season. Use for questions about golden boot, top scorer, most goals in a league.",
            "parameters": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "League ID: 39=Premier League, 140=La Liga, 78=Bundesliga, 135=Serie A, 61=Ligue 1"},
                "season":    {"type": "integer", "description": "Season year. Always default to 2024."}
            },
            "required": ["league_id", "season"]
        }
    }
}
]


# ─── Tool functions ───────────────────────────────────────────────────────────

def get_standings(league_id: int, season: int) -> str:
    try:
        resp = requests.get(f"{FOOTBALL_BASE}/standings",
            headers=FOOTBALL_HEADERS,
            params={"league": league_id, "season": season},
            timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data["response"]:
            return "No standings data found."

        standings   = data["response"][0]["league"]["standings"][0]
        league_name = data["response"][0]["league"]["name"]

        lines = [f"📊 {league_name} {season}/{str(season+1)[-2:]} Standings:\n"]
        for team in standings[:20]:
            r    = team["rank"]
            name = team["team"]["name"]
            pts  = team["points"]
            gd   = team["goalsDiff"]
            w, d, l = team["all"]["win"], team["all"]["draw"], team["all"]["lose"]
            played  = team["all"]["played"]
            lines.append(f"{r:2}. {name:<25} P{played} W{w} D{d} L{l} GD{gd:+} Pts:{pts}")

        print(f"[Tool] get_standings({league_id}, {season}) ✓")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Tool] get_standings failed: {e}")
        return f"Couldn't fetch standings: {e}"

def get_top_scorers(league_id: int, season: int) -> str:
    try:
        resp = requests.get(f"{FOOTBALL_BASE}/players/topscorers",
            headers=FOOTBALL_HEADERS,
            params={"league": league_id, "season": season},
            timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data["response"]:
            return "No top scorer data found."

        lines = [f"🥅 Top Scorers {season}/{str(season+1)[-2:]}:\n"]
        for i, entry in enumerate(data["response"][:10], 1):
            player = entry["player"]["name"]
            team   = entry["statistics"][0]["team"]["name"]
            goals  = entry["statistics"][0]["goals"]["total"]
            lines.append(f"{i:2}. {player:<25} ({team}) — {goals} goals")

        print(f"[Tool] get_top_scorers({league_id}, {season}) ✓")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Tool] get_top_scorers failed: {e}")
        return f"Couldn't fetch top scorers: {e}"

def get_fixtures(league_id: int = None, season: int = None,
                 team_id: int = None, today: bool = False) -> str:
    try:
        params = {}
        if today or (not team_id and not league_id):
            params["date"] = dt.date.today().isoformat()
        if league_id: params["league"] = league_id
        if season:    params["season"] = season
        if team_id:   params["team"]   = team_id

        resp = requests.get(f"{FOOTBALL_BASE}/fixtures",
            headers=FOOTBALL_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data     = resp.json()
        fixtures = data["response"]

        if not fixtures:
            return f"No fixtures found for those parameters."

        label = f"today ({dt.date.today()})" if today or "date" in params else f"season {season}"
        lines = [f"📅 Fixtures ({label}) — {len(fixtures)} matches:\n"]

        for f in fixtures[:15]:
            home   = f["teams"]["home"]["name"]
            away   = f["teams"]["away"]["name"]
            date   = f["fixture"]["date"][:10]
            status = f["fixture"]["status"]["short"]
            if status == "FT":
                gh = f["goals"]["home"]
                ga = f["goals"]["away"]
                lines.append(f"✅ {date} | {home} {gh}-{ga} {away} (FT)")
            elif status in ("1H", "2H", "HT"):
                gh = f["goals"]["home"]
                ga = f["goals"]["away"]
                lines.append(f"🔴 LIVE | {home} {gh}-{ga} {away}")
            else:
                time_ = f["fixture"]["date"][11:16]
                lines.append(f"🗓️  {date} {time_} UTC | {home} vs {away}")

        print(f"[Tool] get_fixtures → {len(fixtures)} results")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Tool] get_fixtures failed: {e}")
        return f"Couldn't fetch fixtures: {e}"


def get_live_scores(league_id: int = None) -> str:
    try:
        params = {"live": "all"}
        if league_id: params["live"] = str(league_id)

        resp = requests.get(f"{FOOTBALL_BASE}/fixtures",
            headers=FOOTBALL_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        fixtures = resp.json()["response"]

        if not fixtures:
            return "No live matches right now."

        lines = ["🔴 LIVE SCORES:\n"]
        for f in fixtures:
            home   = f["teams"]["home"]["name"]
            away   = f["teams"]["away"]["name"]
            gh     = f["goals"]["home"]
            ga     = f["goals"]["away"]
            minute = f["fixture"]["status"].get("elapsed", "?")
            league = f["league"]["name"]
            lines.append(f"⚽ {league} | {home} {gh}-{ga} {away} ({minute}')")

        print(f"[Tool] get_live_scores → {len(fixtures)} live")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Tool] get_live_scores failed: {e}")
        return f"Couldn't fetch live scores: {e}"


def get_player_stats(player_id: int, season: int) -> str:
    try:
        resp = requests.get(f"{FOOTBALL_BASE}/players",
            headers=FOOTBALL_HEADERS,
            params={"id": player_id, "season": season},
            timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data["response"]:
            return "No player data found."

        player   = data["response"][0]["player"]
        stats    = data["response"][0]["statistics"][0]  # first league they played in

        name        = player["name"]
        nationality = player["nationality"]
        age         = player["age"]
        club        = stats["team"]["name"]
        league      = stats["league"]["name"]
        appearances = stats["games"]["appearences"] or 0
        goals       = stats["goals"]["total"] or 0
        assists     = stats["goals"]["assists"] or 0
        yellow      = stats["cards"]["yellow"] or 0
        red         = stats["cards"]["red"] or 0
        rating      = stats["games"]["rating"] or "N/A"

        lines = [
            f"👤 {name} ({nationality}, age {age})",
            f"🏟️  Club: {club} | League: {league} | Season: {season}/{str(season+1)[-2:]}",
            f"📊 Appearances: {appearances}",
            f"⚽ Goals: {goals}  |  🎯 Assists: {assists}",
            f"🟨 Yellow cards: {yellow}  |  🟥 Red cards: {red}",
            f"⭐ Avg rating: {rating}",
        ]

        print(f"[Tool] get_player_stats({player_id}, {season}) → {name} ✓")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Tool] get_player_stats failed: {e}")
        return f"Couldn't fetch player stats: {e}"


TOOL_FUNCTIONS = {
    "get_standings":    get_standings,
    "get_fixtures":     get_fixtures,
    "get_live_scores":  get_live_scores,
    "get_player_stats": get_player_stats,
    "get_top_scorers":  get_top_scorers,
}


# ─── Embedding helper ─────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float] | None:
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            json={"model": "qwen/qwen3-embedding-4b", "input": text, "encoding_format": "float"},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}", "Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and data["data"]:
            return data["data"][0]["embedding"]
        elif "embedding" in data:
            return data["embedding"]
    except Exception as e:
        print(f"[Embedding] Failed: {e}")
    return None


# ─── Agent 3: Memory retrieval ────────────────────────────────────────────────

def retrieve_memories(user_message: str, top_k: int = 3) -> str:
    if memory_collection.count() == 0:
        return ""

    query_vector = get_embedding(user_message)
    if query_vector is None:
        return ""

    results = memory_collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, memory_collection.count()),
        include=["documents", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]

    top_memories = []
    for doc, dist in zip(documents, distances):
        similarity = 1 - (dist / 2)
        if similarity > 0.5:
            top_memories.append(doc)

    if not top_memories:
        return ""

    memory_block = "Relevant things you remember about this user:\n"
    for i, mem in enumerate(top_memories, 1):
        memory_block += f"  {i}. {mem}\n"

    print(f"[Agent 3] Injecting {len(top_memories)} memories into Agent 1 context")
    return memory_block


# ─── Agent 2: Memory extraction ───────────────────────────────────────────────

def extract_memory(user_message: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        response_text = resp.json()["message"]["content"].strip()
    except Exception as e:
        print(f"[Agent 2] Ollama call failed: {e}")
        return "No memory to store"

    memory_data: dict = {}
    try:
        memory_data = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*?\}', response_text, re.DOTALL)
        if match:
            try:
                memory_data = json.loads(match.group())
            except json.JSONDecodeError:
                return "No memory to store"
        else:
            return "No memory to store"

    imp_text = memory_data.get("imp")
    if not imp_text or not str(imp_text).strip() or str(imp_text).lower() == "null":
        print("[Agent 2] No memory to store")
        return "No memory to store"

    imp_text = str(imp_text).strip()

    embedding_vector = get_embedding(imp_text)
    if embedding_vector is None:
        return "No memory to store"

    # Deduplication
    if memory_collection.count() > 0:
        existing = memory_collection.query(
            query_embeddings=[embedding_vector],
            n_results=1,
            include=["distances"],
        )
        if existing["distances"][0]:
            similarity = 1 - (existing["distances"][0][0] / 2)
            print(f"[Agent 2] Similarity check: {similarity:.4f}")
            if similarity > 0.95:
                print(f"[Agent 2] Duplicate skipped ({similarity:.4f}): {imp_text}")
                return "Duplicate — not stored"

    try:
        memory_collection.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding_vector],
            documents=[imp_text],
            metadatas=[{"timestamp": datetime.now().isoformat()}],
        )
        print(f"[Agent 2] Memory stored: {imp_text}")
        return f"Memory stored: {imp_text}"
    except Exception as e:
        print(f"[Agent 2] ChromaDB write failed: {e}")
        return "No memory to store"


# ─── Agent 1: Chat with tool calling ─────────────────────────────────────────

def generate_reply(history: list) -> str:
    """
    First call: model decides if it needs a tool.
    If yes: execute tool, second call with real data → final reply.
    If no: return content directly.
    """
    payload = {
        "model":    MODEL,
        "messages": history,
        "tools":    TOOLS,
        "stream":   False,
    }

    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    message = resp.json()["message"]

    if not message.get("tool_calls"):
        return message["content"]

    # Execute all tool calls
    tool_results_messages = []
    for tool_call in message["tool_calls"]:
        fn_name = tool_call["function"]["name"]
        fn_args = tool_call["function"]["arguments"]
        tool_id = tool_call.get("id", fn_name)

        print(f"[Agent 1] Tool call: {fn_name}({fn_args})")

        tool_result = TOOL_FUNCTIONS[fn_name](**fn_args) if fn_name in TOOL_FUNCTIONS else f"Unknown tool: {fn_name}"
        print(f"[Agent 1] Tool result preview: {tool_result[:120]}...")

        tool_results_messages.append({
            "role":         "tool",
            "tool_call_id": tool_id,
            "content":      tool_result,
        })

    # Second call with tool results
    resp2 = requests.post(OLLAMA_URL, json={
        "model":    MODEL,
        "messages": history + [message] + tool_results_messages,
        "stream":   False,
    }, timeout=120)
    resp2.raise_for_status()
    return resp2.json()["message"]["content"]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data       = request.get_json(force=True)
    user_msg   = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    # Agent 3 — retrieve memories
    relevant_memories     = retrieve_memories(user_msg)
    enriched_system_prompt = SYSTEM_PROMPT + ("\n\n" + relevant_memories if relevant_memories else "")

    if session_id not in conversation_store:
        conversation_store[session_id] = [{"role": "system", "content": enriched_system_prompt}]
    else:
        conversation_store[session_id][0] = {"role": "system", "content": enriched_system_prompt}

    history = conversation_store[session_id]
    history.append({"role": "user", "content": user_msg})

    # Agent 1 + Agent 2 in parallel
    executor      = ThreadPoolExecutor(max_workers=2)
    future_reply  = executor.submit(generate_reply, list(history))
    future_memory = executor.submit(extract_memory, user_msg)

    try:
        assistant_msg = future_reply.result()
    except requests.exceptions.ConnectionError:
        executor.shutdown(wait=False)
        return jsonify({"error": "Cannot connect to Ollama. Make sure it is running on port 11434."}), 503
    except requests.exceptions.Timeout:
        executor.shutdown(wait=False)
        return jsonify({"error": "Request timed out. The model may be slow — try again."}), 504
    except Exception as exc:
        executor.shutdown(wait=False)
        return jsonify({"error": str(exc)}), 500

    history.append({"role": "assistant", "content": assistant_msg})

    def _watch_agent2():
        try:
            result = future_memory.result()
            print(f"[Agent 2] {result}")
        except Exception as e:
            print(f"[Agent 2 error] {e}")
        finally:
            executor.shutdown(wait=False)

    ThreadPoolExecutor(max_workers=1).submit(_watch_agent2)

    return jsonify({"reply": assistant_msg})


@app.route("/api/reset", methods=["POST"])
def reset():
    data       = request.get_json(force=True)
    session_id = data.get("session_id", "default")
    conversation_store.pop(session_id, None)
    return jsonify({"status": "ok"})


@app.route("/api/memories", methods=["GET"])
def view_memories():
    try:
        results  = memory_collection.get(include=["documents", "metadatas"])
        memories = [
            {"id": id_, "memory": doc, "timestamp": meta.get("timestamp", "unknown")}
            for doc, meta, id_ in zip(results["documents"], results["metadatas"], results["ids"])
        ]
        memories.sort(key=lambda x: x["timestamp"], reverse=True)
        return jsonify({"total": len(memories), "memories": memories})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("\n📋 View memories: http://127.0.0.1:5000/api/memories\n")
    app.run(debug=True, port=5000)