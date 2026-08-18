"""Testa o pipeline completo: feeds -> agent -> formatacao.
Nao sobe o bot, nao conflita com o pod no k3s.

Uso:
    source .venv/bin/activate
    set -a && source .env && set +a
    python3 test_digest.py
"""
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))
os.chdir(_ROOT)

import store
import feeds
import agent
import market
import telegram

print("=== Abrindo banco ===")
conn = store.open_db()

print("\n=== Coletando candidatos ===")
candidates = feeds.collect_new(conn)
print(f"Candidatos encontrados: {len(candidates)}")
if not candidates:
    print("Nenhum candidato novo. Banco pode estar com todos os itens marcados como vistos.")
    print("Delete o news.db e rode de novo para forçar uma coleta fresca.")
    sys.exit(0)

for c in candidates[:5]:
    print(f"  - [{c['source']}] {c['title'][:80]}")
if len(candidates) > 5:
    print(f"  ... e mais {len(candidates) - 5}")

print("\n=== Cotações ===")
quotes, quotes_spoken = market.get_quotes()
print(quotes or "Cotações indisponíveis")

print("\n=== Rodando curadoria (agent) ===")
digest, input_tokens, output_tokens = agent.curate(candidates)

if digest:
    print(f"Digest gerado com {len(digest)} itens ({input_tokens} input / {output_tokens} output tokens)")
else:
    print("Agent indisponivel ou falhou — digest sera lista crua")

print("\n=== Mensagem final (Telegram) ===")
text = telegram.format_digest(digest, candidates, has_podcast=True, quotes=quotes)
print(text)
