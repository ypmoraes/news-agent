"""Testa o pipeline completo com podcast: feeds -> agent -> cotacoes -> podcast -> MP3.
Salva o audio em tests/test_podcast.mp3 para ouvir pelo Windows Explorer.

Uso:
    source .venv/bin/activate
    set -a && source .env && set +a
    python3 tests/test_podcast.py
"""
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))
os.chdir(_ROOT)

import store
import feeds
import agent
import market
import podcast
import telegram

print("=== Abrindo banco ===")
conn = store.open_db()

print("\n=== Coletando candidatos ===")
candidates = feeds.collect_new(conn)
print(f"Candidatos encontrados: {len(candidates)}")
if not candidates:
    print("Nenhum candidato novo. Delete o news.db e rode de novo.")
    sys.exit(0)

print("\n=== Cotações ===")
quotes = market.get_quotes()
print(quotes or "Cotações indisponíveis")

print("\n=== Rodando curadoria (agent) ===")
digest, input_tokens, output_tokens = agent.curate(candidates)
if digest:
    print(f"Digest gerado com {len(digest)} itens ({input_tokens} input / {output_tokens} output tokens)")
else:
    print("Agent indisponivel — abortando (podcast requer digest curado)")
    sys.exit(1)

print("\n=== Gerando roteiro ===")
script = podcast.generate_script(digest, quotes=quotes)
if not script:
    print("ERRO: roteiro nao gerado")
    sys.exit(1)
print(f"Roteiro ({len(script)} chars):\n")
print(script)

print("\n=== Sintetizando audio ===")
mp3 = podcast.synthesize(script)
if not mp3:
    print("ERRO: audio nao gerado")
    sys.exit(1)
print(f"Audio MP3: {len(mp3)} bytes")

output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_podcast.mp3")
with open(output, "wb") as f:
    f.write(mp3)

print("\n=== Mensagem final (Telegram) ===")
text = telegram.format_digest(digest, candidates, has_podcast=True, quotes=quotes)
print(text)

print(f"\n=== Pronto! ===")
print(f"Audio salvo em: {output}")
print("Abra pelo Windows Explorer para ouvir.")
