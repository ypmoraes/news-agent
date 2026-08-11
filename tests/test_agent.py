import os, json, requests

key = os.environ.get('ANTHROPIC_API_KEY', '')
print('key:', key[:15] if key else 'NONE')

FETCH_TOOL = {
    "name": "fetch_article",
    "description": "Fetch the full readable text of a news article by URL.",
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string"}},
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
    except Exception as exc:
        return f"(fetch error: {exc})"

candidates = [
    {"source": "TechCrunch", "title": "OpenAI launches new model", "url": "https://example.com/1", "summary": "OpenAI released GPT-5 today."},
    {"source": "The Verge", "title": "Microsoft Azure outage", "url": "https://example.com/2", "summary": "Azure had a major outage affecting EU regions."},
]

messages = [{"role": "user", "content": "Candidate stories (JSON):\n" + json.dumps(candidates)}]
headers = {
    "x-api-key": key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

for round_num in range(8):
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "system": 'Pick top stories and reply ONLY with JSON: {"digest": [{"title":"...","source":"...","url":"...","why":"...","short_hook":null}]}',
        "tools": [FETCH_TOOL],
        "messages": messages,
    }

    print(f"\n--- Round {round_num + 1} ---")
    print(f"Sending {len(messages)} messages")
    resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=120)
    print("Status:", resp.status_code)
    data = resp.json()
    print("stop_reason:", data.get("stop_reason"))
    print("content block types:", [b.get("type") for b in data.get("content", [])])

    messages.append({"role": "assistant", "content": data["content"]})

    if data.get("stop_reason") == "tool_use":
        results = []
        for block in data["content"]:
            if block.get("type") == "tool_use" and block.get("name") == "fetch_article":
                url = block["input"].get("url", "")
                print(f"  fetching: {url}")
                article = _fetch_article(url)
                print(f"  result: {article[:80]}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": article,
                })
        messages.append({"role": "user", "content": results})
        continue

    # final response
    text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
    print("\nFinal text (first 500 chars):")
    print(repr(text[:500]))
    break
else:
    print("Hit round cap without final answer")
