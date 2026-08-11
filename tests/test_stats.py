"""Testa o envio do stats semanal para o admin via Telegram.

Uso:
    source .venv/bin/activate
    set -a && source .env && set +a
    python3 tests/test_stats.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))
os.chdir(_ROOT)

import store
import main

print("=== Abrindo banco ===")
conn = store.open_db()

print("\n=== Enviando stats para o admin ===")
main.send_weekly_stats(conn)
print("Pronto. Verifique o Telegram.")
