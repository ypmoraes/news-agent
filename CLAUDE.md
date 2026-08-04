# news-agent

Bot de Telegram sempre de pé que entrega um digest matinal de notícias de tech,
curado por um agent (Anthropic API), rodando no k3s de um laptop-servidor.

## Estrutura
- `app/` — Python (módulos flat, sem package): `config`, `store`, `feeds`,
  `agent`, `telegram`, `main`.
- `k8s/` — manifestos: namespace, pvc, configmap, secret.example, deployment,
  kustomization.
- `Dockerfile`, `requirements.txt`, `DEPLOY-k3s.md`.

## Como o app funciona
- Processo único e sempre de pé (`app/main.py`): faz long polling de comandos do
  Telegram (`/start`, `/stop`, `/list`, `/now`) e, no mesmo loop, um scheduler
  interno dispara o digest no horário `NEWS_DIGEST_TIME`.
- Estado em SQLite (`store.py`): tabelas `seen` (dedup), `subscribers`, `state`.
- Sem `ANTHROPIC_API_KEY`, o agent é pulado e o bot envia a lista crua.

## Rodar e testar
- Deps: `pip install -r requirements.txt`
- Local: exporte `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` e
  `NEWS_DB_PATH=./news.db`, depois `python app/main.py`.
- Config é 100% por variável de ambiente — ver `app/config.py`.

## Build e deploy (k3s) — LER ANTES DE MEXER
- **k3s usa containerd, NÃO o Docker.** Depois de
  `docker build -t news-agent:latest .`, é OBRIGATÓRIO
  `docker save news-agent:latest -o news-agent.tar && sudo k3s ctr images import news-agent.tar`.
  Sem isso o pod fica em `ErrImageNeverPull`.
- Deploy: `kubectl apply -k k8s/`.
- Deployment é `replicas: 1` + `strategy: Recreate` de propósito: SQLite é
  single-writer no PVC. **Não escalar réplicas** — long polling não suporta duas
  instâncias.

## Convenções
- Não commitar segredos: `k8s/secret.yaml` e `.env` estão no `.gitignore`.
  Criar o Secret de forma imperativa (ver `DEPLOY-k3s.md`).
- Não editar/commitar `seen.db` / `news.db` (estado de runtime).
- Ao mudar as fontes RSS (`app/config.py`) ou o Dockerfile, lembrar de
  rebuild + reimport da imagem no k3s.
