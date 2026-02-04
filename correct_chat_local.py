import json
import os
import re
import time
from pathlib import Path
from urllib import request

PROMPT = """Tu es un correcteur orthographique et typographique.
Ta mission : corriger les fautes de frappe/orthographe/grammaire dans un export WhatsApp.
Contraintes STRICTES :
- Ne jamais modifier les timestamps entre crochets, ni les noms dauteurs.
- Ne pas traduire. Conserver la langue d'origine de chaque segment (francais, anglais, hebreu).
- Ne pas changer le sens.
- Fusionner les messages multilignes dun meme auteur : le texte doit etre sur UNE seule ligne apres lentete.
- Conserver le format exact : [DD/MM/YYYY HH:MM:SS] Nom: Message
- Garder les pieces jointes intactes, par ex : < piece jointe : ... >
- Conserver les emojis.

Entree : contenu integral de _chat.txt
Sortie : contenu corrige integral  ecrire dans _chat_corrected.txt
Aucune explication, seulement le texte corrige final.
"""

INPUT_FILE = Path("_chat.txt")
OUTPUT_FILE = Path("_chat_corrected.txt")
PAGES_DIR = Path("_chat_pages")
STATE_FILE = Path("_chat_pages/state.json")


def load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv(Path(".env"))

# OpenAI API settings
API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Simple chunking to avoid context limits
MAX_CHARS = int(os.environ.get("LOCAL_OPENAI_MAX_CHARS", "30000"))
MERGE_ONLY = os.environ.get("LOCAL_OPENAI_MERGE_ONLY", "").lower() in (
    "1",
    "true",
    "yes",
)


MSG_HEADER_RE = re.compile(r"^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\] .+?:")


def split_messages(text):
    messages = []
    current = []
    for line in text.splitlines():
        if MSG_HEADER_RE.match(line) and current:
            messages.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        messages.append("\n".join(current))
    return messages


def chunk_messages(messages, max_chars):
    chunks = []
    current = []
    size = 0
    for msg in messages:
        msg_len = len(msg) + 1
        if current and size + msg_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(msg)
        size += msg_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def call_openai(messages):
    if not API_KEY:
        raise SystemExit("OPENAI_API_KEY is not set.")
    url = f"{API_BASE}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    with request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)["choices"][0]["message"]["content"]


def normalize_output(text):
    # Ensure no leading/trailing whitespace changes beyond necessary
    return text.strip("\n") + "\n"


def load_state():
    if not STATE_FILE.exists():
        return {"completed": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"completed": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    if not INPUT_FILE.exists():
        raise SystemExit(f"Input file not found: {INPUT_FILE}")

    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Pages dir: {PAGES_DIR}")

    raw = INPUT_FILE.read_text(encoding="utf-8")
    messages = split_messages(raw)
    chunks = chunk_messages(messages, MAX_CHARS)
    PAGES_DIR.mkdir(exist_ok=True)

    state = load_state()
    completed = set(state.get("completed", []))

    outputs = []
    if MERGE_ONLY:
        print("Mode: merge only")
        for page_path in sorted(PAGES_DIR.glob("page_*.txt")):
            outputs.append(page_path.read_text(encoding="utf-8").strip("\n"))
        corrected = "\n".join(outputs).strip("\n") + "\n"
        OUTPUT_FILE.write_text(normalize_output(corrected), encoding="utf-8")
        print(f"Wrote: {OUTPUT_FILE}")
        print(f"Pages in: {PAGES_DIR}")
        return

    print(f"Total pages to process: {len(chunks)}")
    if completed:
        print(f"Already completed: {len(completed)} pages")

    for i, chunk in enumerate(chunks, start=1):
        msg_count = chunk.count("\n") + 1 if chunk.strip() else 0
        page_name = f"page_{i:04d}.txt"
        page_path = PAGES_DIR / page_name

        if i in completed and page_path.exists():
            print(f"[{i}/{len(chunks)}] Skip (already done): {page_name} ({msg_count} messages)")
            outputs.append(page_path.read_text(encoding="utf-8").strip("\n"))
            continue

        print(f"[{i}/{len(chunks)}] Processing: {page_name} ({len(chunk)} chars, {msg_count} messages)")
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": chunk},
        ]
        result = call_openai(messages)
        page_path.write_text(normalize_output(result), encoding="utf-8")
        outputs.append(result.strip("\n"))

        completed.add(i)
        save_state({"completed": sorted(completed)})
        print(f"[{i}/{len(chunks)}] Done: {page_name}")

        # small delay if the local server needs breathing room
        time.sleep(0.2)

    corrected = "\n".join(outputs).strip("\n") + "\n"
    OUTPUT_FILE.write_text(normalize_output(corrected), encoding="utf-8")
    print(f"Wrote: {OUTPUT_FILE}")
    print(f"Pages in: {PAGES_DIR}")
    print("Completed all pages.")


if __name__ == "__main__":
    main()
