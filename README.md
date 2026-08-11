# News Agent — bot de inscritos (always-on / k3s)

Bot de Telegram sempre de pé que entrega um **digest matinal de tech e
economia, curado por um agent**, com **podcast em áudio**, **cotações do
dia** e **memória semântica** entre edições (evita repetir a mesma notícia).
As pessoas se inscrevem sozinhas com `/start`; de segunda a sexta, no horário
`NEWS_DIGEST_TIME`, o resumo é enviado a todos. Roda como um Deployment no
k3s.

## Como funciona

Um único processo (Deployment `replicas: 1`) faz três coisas ao mesmo tempo:

- **Escuta comandos** via long polling do Telegram — sem porta exposta, só
  tráfego de saída.
- **Auto-agenda o digest**: a cada ciclo verifica se já passou de
  `DIGEST_TIME` (dias úteis) e, uma vez por dia, busca os feeds, cura com o
  agent, gera o podcast e faz broadcast.
- **Auto-agenda stats**: às sextas, manda ao admin um resumo da semana
  (edições, assinantes, notícias, custo estimado de Claude e uso de
  ElevenLabs).

A curadoria usa Claude com uma tool (`fetch_article`) para ler o texto
completo de uma notícia quando o resumo do RSS é fraco demais para julgar
importância. Antes de curar, o agent consulta um banco vetorial local
(ChromaDB) com o histórico dos últimos dias, pra não repetir cobertura e
enquadrar desdobramentos. Sem `ANTHROPIC_API_KEY`, a curadoria e o podcast
são pulados e o bot manda a lista crua dos feeds.

Estado (dedup + inscritos + offset + log de custos) vive num SQLite sobre um
PVC; a memória vetorial vive num ChromaDB (arquivo local) no mesmo PVC. Como
o SQLite é single-writer, o Deployment usa `strategy: Recreate` e
`replicas: 1`.

### Comandos

| Comando  | Quem  | O que faz |
|----------|-------|-----------|
| `/start` | qualquer um | inscreve o remetente e manda a mensagem de intro |
| `/stop`  | qualquer um | remove o remetente |
| `/sobre` | qualquer um | sobre o bot + fontes monitoradas |
| `/projeto` | qualquer um | explica as tecnologias e o método de criação do bot |
| `/help`  | qualquer um | lista de comandos |
| `/list`  | admin | lista os inscritos |
| `/now`   | admin | dispara o digest na hora (teste) |
| `/stats` | admin | stats da semana + custo estimado |

Quem bloqueia o bot (erro 403 no envio) é removido da lista automaticamente.

## Estrutura

```
app/
  config.py     env + feeds
  store.py      SQLite: seen / subscribers / state / digest_log (custos)
  feeds.py      coleta RSS + dedup
  agent.py      curadoria (LLM + tool fetch_article)
  memory.py     memória semântica (ChromaDB + sentence-transformers)
  market.py     cotações USD/EUR-BRL (AwesomeAPI)
  podcast.py    roteiro (Claude) + TTS (ElevenLabs) + conversão OGG (pydub)
  telegram.py   getUpdates, sendMessage, sendAudio, broadcast, formatação
  main.py       loop: comandos + scheduler do digest + scheduler de stats
k8s/            namespace, pvc, configmap, secret.example, deployment, kustomization
tests/          testes unitários (agent, feeds, memory, podcast, stats, digest, api)
ops/
  Dockerfile
  deploy.sh       deploy automatizado (rsync + build + import + apply) num servidor remoto
  DEPLOY-k3s.md   passo a passo manual no servidor
```

## Configuração (variáveis de ambiente)

Ver `app/config.py` para a lista completa e os defaults. As principais:

| Variável | Descrição |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ADMIN_CHAT_ID` | credenciais do bot e chat autorizado a rodar comandos de admin |
| `ANTHROPIC_API_KEY` / `NEWS_MODEL` | ativa curadoria + podcast; sem a key, roda em modo cru |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | ativa geração de áudio do podcast |
| `NEWS_DIGEST_TIME` / `NEWS_TZ` | horário e fuso do digest diário |
| `NEWS_MAX_CANDIDATES` / `NEWS_MAX_DIGEST` | quantos itens coletar / quantos entram no digest curado |
| `NEWS_MEMORY_ENABLED` / `NEWS_MEMORY_WINDOW_DAYS` | liga/desliga a memória semântica e a janela de dias considerada |
| `NEWS_ENABLE_SHORTS` | pede ao agent um gancho de YouTube Short por notícia |
| `NEWS_DB_PATH` | caminho do SQLite (e da pasta `chroma/` da memória, ao lado) |

## Rodar localmente

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=... TELEGRAM_ADMIN_CHAT_ID=... NEWS_DB_PATH=./news.db
python app/main.py
```

`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` são
opcionais — sem eles o bot roda sem curadoria/podcast.

## Deploy

Veja `ops/DEPLOY-k3s.md` para o passo a passo manual, ou `ops/deploy.sh`
(rodar a partir da raiz do repo) para automatizar rsync + build + import no
containerd do k3s + `kubectl apply` contra um servidor remoto (ajuste
`SERVER` e a chave SSH no início do script). Resumo: instalar k3s →
`docker build -f ops/Dockerfile .` → exportar e `k3s ctr images import` →
criar Secret → `kubectl apply -k k8s/`.

## Ligar o canal de Shorts

Ponha `NEWS_ENABLE_SHORTS=true` no ConfigMap: cada notícia curada passa a vir
com um gancho de YouTube Short — seu digest matinal vira também sua pauta.

## Ponte pro Grafana (próxima etapa)

O bot já registra custo/uso por edição em `digest_log` (SQLite); falta expor
isso num endpoint HTTP pra um Grafana rodando no mesmo k3s virar seu primeiro
dashboard com dado próprio.
