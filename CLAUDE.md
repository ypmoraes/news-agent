# news-agent

Bot de Telegram sempre de pé que entrega um digest matinal de notícias de tech
e economia, curado por um agent (Anthropic API), com podcast em áudio
(ElevenLabs), cotações do dia e memória semântica entre edições (ChromaDB).
Roda no k3s de um laptop-servidor.

## Estrutura
- `app/` — Python (módulos flat, sem package): `config`, `store`, `feeds`,
  `agent` (curadoria + tool `fetch_article`), `memory` (RAG: ChromaDB +
  sentence-transformers), `market` (cotações USD/EUR-BRL), `podcast`
  (roteiro via Claude + TTS via ElevenLabs + conversão OGG via pydub),
  `telegram`, `main`.
- `k8s/` — manifestos: namespace, pvc, configmap, secret.example, deployment,
  kustomization.
- `ops/` — `Dockerfile`, `DEPLOY-k3s.md` (passo a passo manual) e `deploy.sh`
  (deploy automatizado via rsync/ssh contra um servidor remoto fixo; rodar a
  partir da raiz do repo: `ops/deploy.sh`).
- `requirements.txt` na raiz.

## Como o app funciona
- Processo único e sempre de pé (`app/main.py`): faz long polling de comandos do
  Telegram (`/start`, `/stop`, `/sobre`, `/projeto`, `/help`, `/list`, `/now`,
  `/stats`) e,
  no mesmo loop, um scheduler interno dispara o digest (dias úteis, no horário
  `NEWS_DIGEST_TIME`) e o resumo semanal de stats pro admin (sextas).
- Antes de curar, `memory.py` busca no ChromaDB notícias semanticamente
  similares dos últimos `NEWS_MEMORY_WINDOW_DAYS` dias e injeta como contexto
  no prompt do agent, pra evitar repetir cobertura. `NEWS_MEMORY_ENABLED=true`
  por padrão.
- Depois de curado, `podcast.py` gera um roteiro (Claude) e sintetiza áudio
  (ElevenLabs), enviado como MP3 no Telegram junto com o texto do digest.
- Estado em SQLite (`store.py`): tabelas `seen` (dedup), `subscribers`,
  `state`, `digest_log` (custo/uso por edição — tokens Anthropic, chars
  ElevenLabs). A memória vetorial vive num ChromaDB (arquivo local) na mesma
  pasta do `NEWS_DB_PATH`.
- Sem `ANTHROPIC_API_KEY`, o agent e o podcast são pulados e o bot envia a
  lista crua.

## Rodar e testar
- Deps: `pip install -r requirements.txt`
- Local: exporte `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` e
  `NEWS_DB_PATH=./news.db`, depois `python app/main.py`.
- Config é 100% por variável de ambiente — ver `app/config.py`.
- Testes em `tests/` (um arquivo por módulo: `agent`, `feeds`, `memory`,
  `podcast`, `stats`, `digest`, `api`).

## Build e deploy (k3s) — LER ANTES DE MEXER
- O Dockerfile fica em `ops/Dockerfile`; o build context continua sendo a
  raiz do repo: `docker build -f ops/Dockerfile -t news-agent:latest .`
- **k3s usa containerd, NÃO o Docker.** Depois do build, é OBRIGATÓRIO
  `docker save news-agent:latest -o news-agent.tar && sudo k3s ctr images import news-agent.tar`.
  Sem isso o pod fica em `ErrImageNeverPull`.
- Deploy: `kubectl apply -k k8s/`.
- Deployment é `replicas: 1` + `strategy: Recreate` de propósito: SQLite é
  single-writer no PVC. **Não escalar réplicas** — long polling não suporta duas
  instâncias.

## Convenções
- Não commitar segredos: `k8s/secret.yaml`, `secret.yaml` (raiz) e `.env`
  estão no `.gitignore`. Preferir criar o Secret de forma imperativa (ver
  `ops/DEPLOY-k3s.md`) em vez de manter valores reais em arquivo.
- Não editar/commitar `seen.db` / `news.db` (estado de runtime) nem a pasta
  `chroma/` (memória vetorial).
- Ao mudar as fontes RSS (`app/config.py`) ou `ops/Dockerfile`, lembrar de
  rebuild + reimport da imagem no k3s.
