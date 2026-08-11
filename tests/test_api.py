import os, requests
key = os.environ.get('ANTHROPIC_API_KEY', '')
print('key:', key[:15] if key else 'NONE')
r = requests.post(
    'https://api.anthropic.com/v1/messages',
    headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
    json={'model': 'claude-haiku-4-5-20251001', 'max_tokens': 50, 'messages': [{'role': 'user', 'content': 'Say hello'}]},
    timeout=30
)
print('status:', r.status_code)
print('resp:', r.text[:300])
