"""Curation agent: reads full articles via a tool, then ranks and annotates.

Returns None when no ANTHROPIC_API_KEY is set, so the caller falls back to a
plain uncurated list.
"""
import json
import logging

import requests

import config

log = logging.getLogger("agent")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

FETCH_TOOL = {
    "name": "fetch_article",
    "description": (
        "Fetch the full readable text of a news article by URL. Use this when the "
        "RSS summary is too thin to judge importance or to write an accurate "
        "'why it matters'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The article URL"}},
        "required": ["url"],
    },
}


def _fetch_article(url):
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return "(could not download the article)"
        text = trafilatura.extract(downloaded, include_comments=False)
        return text[:6000] if text else "(no extractable text)"
    except Exception as exc:  # noqa: BLE001
        return f"(fetch error: {exc})"


def _system_prompt():
    parts = [
        "You are the editor of a personal morning tech-news digest for a senior "
        "DevOps / cloud infrastructure engineer. Interests: AI, cloud, Azure, "
        "Linux, SQL Server, security, developer tooling.",
        "You receive a list of candidate stories pulled from RSS feeds. Your job:",
        "1. Drop noise, duplicates, and anything off-topic for that reader.",
        "2. When a story looks important but its summary is thin, call fetch_article "
        "to read the full text before deciding.",
        f"3. Pick the top {config.MAX_DIGEST} stories, ranked by importance.",
        "4. For each, write one crisp sentence of 'why it matters', in clear English.",
    ]
    if config.ENABLE_SHORTS:
        parts.append(
            "5. If a story would make a good YouTube Short, set short_hook to a punchy "
            "one-line English hook; otherwise null."
        )
    parts.append(
        'When finished, reply with ONLY a JSON object, no prose and no markdown '
        'fences: {"digest": [{"title": "...", "source": "...", "url": "...", '
        '"why": "...", "short_hook": null}]}'
    )
    return "\n".join(parts)


def curate(candidates):
    if not config.ANTHROPIC_API_KEY:
        log.info("no ANTHROPIC_API_KEY; using raw list")
        return None

    payload = [
        {"source": c["source"], "title": c["title"], "url": c["url"], "summary": c["summary"]}
        for c in candidates
    ]
    messages = [{"role": "user", "content": "Candidate stories (JSON):\n" + json.dumps(payload, ensure_ascii=False)}]
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    for _ in range(8):
        body = {
            "model": config.MODEL,
            "max_tokens": 2000,
            "system": _system_prompt(),
            "tools": [FETCH_TOOL],
            "messages": messages,
        }
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=120)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("agent request failed: %s", exc)
            return None

        data = resp.json()
        messages.append({"role": "assistant", "content": data["content"]})

        if data.get("stop_reason") == "tool_use":
            results = []
            for block in data["content"]:
                if block.get("type") == "tool_use" and block.get("name") == "fetch_article":
                    article = _fetch_article(block["input"].get("url", ""))
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": article,
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        return _parse(text)

    log.warning("agent hit the round cap without a final answer")
    return None


def _parse(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        return json.loads(t.strip()).get("digest", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse agent JSON: %s", exc)
        return None
