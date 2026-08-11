"""Testa o módulo de memória semântica (ChromaDB + sentence-transformers).

Uso:
    source .venv/bin/activate
    python3 tests/test_memory.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "app"))
os.chdir(_ROOT)

# Ativa memória e aponta ChromaDB para diretório temporário
os.environ["NEWS_MEMORY_ENABLED"] = "true"
os.environ["NEWS_MEMORY_WINDOW_DAYS"] = "7"

import config

_tmpdir = tempfile.TemporaryDirectory()
# Sobrescreve DB_PATH para que o chroma fique no tmpdir
config.DB_PATH = os.path.join(_tmpdir.name, "news.db")

import memory

# Resetar singletons para usar o novo DB_PATH
memory._client = None
memory._collection = None
memory._embedder = None

SAMPLE_DIGEST = [
    {
        "title": "OpenAI lança GPT-5 com capacidades multimodais avançadas",
        "source": "TechCrunch",
        "url": "https://techcrunch.com/openai-gpt5",
        "why": "Primeiro modelo a superar benchmarks humanos em raciocínio complexo.",
    },
    {
        "title": "Azure sofre outage em regiões da Europa",
        "source": "The Verge",
        "url": "https://theverge.com/azure-outage",
        "why": "Afetou 40% das regiões europeus por 4 horas.",
    },
    {
        "title": "Banco Central eleva Selic para 14,75%",
        "source": "Valor Econômico",
        "url": "https://valor.globo.com/selic-alta",
        "why": "Pressão inflacionária força novo aperto monetário.",
    },
]

SIMILAR_CANDIDATES = [
    {
        "title": "OpenAI apresenta GPT-5: novo modelo bate recordes",
        "source": "InfoMoney",
        "url": "https://infomoney.com.br/gpt5",
        "summary": "O novo GPT-5 da OpenAI supera todos os benchmarks anteriores.",
    },
]

UNRELATED_CANDIDATES = [
    {
        "title": "Tour de France 2026: campeão surpreende no sprint final",
        "source": "ESPN",
        "url": "https://espn.com/tour-de-france",
        "summary": "Ciclista conquista etapa em Paris.",
    },
]

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name}" + (f": {detail}" if detail else ""))
        failed += 1


print("\n=== 1. get_memory_db() inicializa sem erro ===")
client, collection = memory.get_memory_db()
check("client não é None", client is not None)
check("collection não é None", collection is not None)

print("\n=== 2. find_similar() retorna None quando coleção vazia ===")
ctx = memory.find_similar(SIMILAR_CANDIDATES)
check("contexto é None com coleção vazia", ctx is None)

print("\n=== 3. save_digest() armazena itens ===")
ok = memory.save_digest(SAMPLE_DIGEST)
check("save_digest retorna True", ok)
check("coleção tem 3 itens", collection.count() == 3)

print("\n=== 4. find_similar() retorna contexto formatado após save_digest() ===")
ctx = memory.find_similar(SIMILAR_CANDIDATES)
check("contexto não é None", ctx is not None)
check("contexto contém 'HISTÓRICO RECENTE'", ctx is not None and "HISTÓRICO RECENTE" in ctx)
check("contexto contém título do OpenAI", ctx is not None and "GPT" in ctx)

print("\n=== 5. find_similar() não retorna contexto para candidatos não relacionados ===")
ctx_unrelated = memory.find_similar(UNRELATED_CANDIDATES)
# Esportes não devem ter similaridade alta com tech/economy
check("contexto é None para assunto não relacionado", ctx_unrelated is None)

print("\n=== 6. save_digest() é idempotente (upsert não duplica) ===")
memory.save_digest(SAMPLE_DIGEST)  # segundo upsert
check("coleção ainda tem 3 itens (sem duplicatas)", collection.count() == 3)

print("\n=== 7. Degradação gratuita com memória desabilitada ===")
# Resetar singletons e desabilitar
memory._client = None
memory._collection = None
config.MEMORY_ENABLED = False

c2, col2 = memory.get_memory_db()
check("get_memory_db retorna (None, None) quando desabilitado", c2 is None and col2 is None)

ctx2 = memory.find_similar(SIMILAR_CANDIDATES)
check("find_similar retorna None quando desabilitado", ctx2 is None)

ok2 = memory.save_digest(SAMPLE_DIGEST)
check("save_digest retorna False quando desabilitado", ok2 is False)

# Cleanup
_tmpdir.cleanup()

print(f"\n=== Resultado: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
