"""Testa se todos os feeds RSS configurados estão acessíveis e retornando itens.

Uso:
    source .venv/bin/activate
    python3 tests/test_feeds.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))
os.chdir(_ROOT)

import feedparser
import config

passed = 0
failed = 0

print(f"Testando {len(config.FEEDS)} feeds...\n")

for name, url in config.FEEDS.items():
    try:
        f = feedparser.parse(url)
        if f.entries:
            print(f"  ✓ {name} ({len(f.entries)} itens) — {f.entries[0].title[:70]}")
            passed += 1
        else:
            print(f"  ✗ {name} — feed vazio ou inacessível (status: {f.get('status', '?')})")
            failed += 1
    except Exception as exc:
        print(f"  ✗ {name} — erro: {exc}")
        failed += 1

print(f"\n=== Resultado: {passed} ok, {failed} com problema ===")
sys.exit(0 if failed == 0 else 1)
