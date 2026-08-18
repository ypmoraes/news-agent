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


def _system_prompt(memory_context=None):
    parts = [
        "You are the editor of a personal morning digest covering technology and economy. "
        "Your reader works in the tech industry and has strong interest in economic and "
        "financial markets, based in Brazil. "
        "Relevant topics: AI, cloud computing, big tech, startups, product and industry trends, "
        "cybersecurity, developer tooling, Brazilian economy, international markets, "
        "interest rates, and tech industry business news. "
        "Always write in Brazilian Portuguese.",
    ]
    if memory_context:
        parts.append(memory_context)
    parts += [
        "You receive a list of candidate stories pulled from RSS feeds. Your job:",
        "1. Drop noise, duplicates, clickbait, sponsored content, and anything off-topic.",
        "2. Balance the selection: include both tech and economy stories when both have relevant news.",
        "3. When a story looks important but its summary is thin, call fetch_article "
        "to read the full text before deciding.",
        f"4. Pick the top {config.MAX_DIGEST} stories, ranked by importance.",
        "5. For each, write one crisp sentence of 'por que importa', in Brazilian Portuguese.",
        "6. Translate the title into natural Brazilian Portuguese, preserving names, "
        "acronyms, and technical terms that are normally kept in English (e.g. company "
        "and product names). If the original title is already in Portuguese, keep it as is.",
    ]
    if config.ENABLE_SHORTS:
        parts.append(
            "7. If a story would make a good YouTube Short, set short_hook to a punchy "
            "one-line English hook; otherwise null."
        )
    parts.append(
        'When finished, reply with ONLY a JSON object, no prose and no markdown '
        'fences: {"digest": [{"title": "...", "source": "...", "url": "...", '
        '"why": "...", "short_hook": null}]}'
    )
    return "\n".join(parts)


def curate(candidates, memory_context=None):
    if not config.ANTHROPIC_API_KEY:
        log.info("no ANTHROPIC_API_KEY; using raw list")
        return None, 0, 0

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

    total_input = 0
    total_output = 0

    for _ in range(8):
        body = {
            "model": config.MODEL,
            "max_tokens": 2000,
            "system": _system_prompt(memory_context),
            "tools": [FETCH_TOOL],
            "messages": messages,
        }
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=120)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("agent request failed: %s", exc)
            return None, 0, 0

        data = resp.json()
        usage = data.get("usage", {})
        total_input += usage.get("input_tokens", 0)
        total_output += usage.get("output_tokens", 0)
        messages.append({"role": "assistant", "content": data["content"]})

        stop_reason = data.get("stop_reason")

        if stop_reason == "tool_use":
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

        if stop_reason == "max_tokens":
            log.warning("agent hit max_tokens; retrying without tools")
            return None, total_input, total_output

        text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        if not text:
            log.warning("agent returned no text (stop_reason=%s)", stop_reason)
            return None, total_input, total_output
        return _parse(text), total_input, total_output

    log.warning("agent hit the round cap without a final answer")
    return None, total_input, total_output


def _parse(text):
    import re
    t = text.strip()
    # Strip a leading code fence (whole response wrapped in ```)
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    # Model returned prose before the JSON — extract the JSON block
    if not t.startswith("{"):
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
        if m:
            t = m.group(1)
        else:
            m = re.search(r'\{"digest".*\}', t, re.DOTALL)
            if m:
                t = m.group()
    try:
        return json.loads(t.strip()).get("digest", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse agent JSON: %s | text[:200]: %s", exc, text[:200])
        return None
