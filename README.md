# News Agent — bot de inscritos (always-on / k3s)

Bot de Telegram sempre de pé que entrega um **digest matinal de notícias de
tech, curado por um agent**. As pessoas se inscrevem sozinhas com `/start`; às
07:00 (fuso configurável) o resumo é enviado a todos. Roda como um Deployment no
k3s.

## Como funciona

Um único processo (Deployment `replicas: 1`) faz duas coisas ao mesmo tempo:

- **Escuta comandos** via long polling do Telegram — sem porta exposta, só
  tráfego de saída.
- **Auto-agenda** o digest: a cada ciclo verifica se já passou de `DIGEST_TIME`
  e, uma vez por dia, busca os feeds, cura com o agent e faz broadcast.

Estado (dedup + inscritos + offset) vive num SQLite sobre um PVC. Como o SQLite
é single-writer, o Deployment usa `strategy: Recreate` e `replicas: 1`.

### Comandos

| Comando | Quem | O que faz |
|---|---|---|
| `/start` | qualquer um | inscreve o remetente |
| `/stop` | qualquer um | remove o remetente |
| `/help` | qualquer um | lista de comandos |
| `/list` | admin | lista os inscritos |
| `/now` | admin | dispara o digest na hora (teste) |

Quem bloqueia o bot (erro 403 no envio) é removido da lista automaticamente.

## Estrutura

```
app/
  config.py     env + feeds
  store.py      SQLite: seen / subscribers / state
  feeds.py      coleta RSS + dedup
  agent.py      curadoria (LLM + tool fetch_article)
  telegram.py   getUpdates, sendMessage, broadcast, formatação
  main.py       loop: comandos + scheduler
k8s/            namespace, pvc, configmap, secret.example, deployment, kustomization
Dockerfile
DEPLOY-k3s.md   passo a passo no servidor
```

## Deploy

Veja `DEPLOY-k3s.md`. Resumo: instalar k3s → `docker build` → exportar e
`k3s ctr images import` → criar Secret → `kubectl apply -k k8s/`.

## Ligar o canal de Shorts

Ponha `NEWS_ENABLE_SHORTS=true` no ConfigMap: cada notícia curada passa a vir
com um gancho de YouTube Short — seu digest matinal vira também sua pauta.

## Ponte pro Grafana (próxima etapa)

O bot pode expor métricas (nº de inscritos, digests enviados, erros) num
endpoint HTTP; aí um Grafana rodando no mesmo k3s lê e vira seu primeiro
dashboard com dado próprio.
