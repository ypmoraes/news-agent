# Deploy no k3s (servidor always-on)

Passo a passo pra subir o bot sempre-de-pé no seu laptop-servidor. Cada fase
tem uma verificação — só avance quando a anterior estiver verde.

## Fase 1 — Instalar o k3s

```bash
curl -sfL https://get.k3s.io | sh -

# usar o kubectl sem sudo (kubeconfig fica protegido por padrão)
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER ~/.kube/config
```

Verificação: `kubectl get nodes` mostra o nó `Ready`.

> O k3s já traz o provisionador `local-path` (usado pelo PVC) e roda como
> serviço systemd — volta sozinho no boot, que é exatamente o que você quer.

## Fase 2 — Levar a imagem pro k3s (a pegadinha)

O k3s usa **containerd**, não o Docker. A imagem que você constrói com
`docker build` fica no Docker e o k3s **não a enxerga**. Você precisa exportar e
importar no containerd do k3s:

```bash
cd /opt/news-agent        # raiz do repo (ops/, app/, k8s/)
docker build -f ops/Dockerfile -t news-agent:latest .

docker save news-agent:latest -o news-agent.tar
sudo k3s ctr images import news-agent.tar
```

Verificação: `sudo k3s ctr images ls | grep news-agent` lista a imagem.
(É por isso que o Deployment usa `imagePullPolicy: IfNotPresent` — pra ele nunca
tentar puxar de um registry.)

## Fase 3 — Criar o Secret

Não versione segredo. Crie de forma imperativa:

```bash
kubectl create namespace news

kubectl -n news create secret generic news-agent-secrets \
  --from-literal=TELEGRAM_BOT_TOKEN='SEU_TOKEN' \
  --from-literal=TELEGRAM_ADMIN_CHAT_ID='SEU_CHAT_ID' \
  --from-literal=ANTHROPIC_API_KEY='sk-ant-...'    # pode deixar vazio p/ rodar sem o agent
```

Verificação: `kubectl -n news get secret news-agent-secrets`.

> `TELEGRAM_ADMIN_CHAT_ID` é o **seu** chat id — só ele pode rodar `/list` e
> `/now`. Pegue com: mande msg pro bot e
> `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"id":[0-9]*'`.

## Fase 4 — Aplicar o resto

Como o Secret já foi criado acima, remova a linha `secret.yaml` do
`k8s/kustomization.yaml` (ou crie um `secret.yaml` a partir do `.example`). Então:

```bash
kubectl apply -k k8s/
```

Verificação:

```bash
kubectl -n news get pods                     # STATUS Running
kubectl -n news logs -f deploy/news-agent    # "bot up; polling. digest at 07:00"
```

## Fase 5 — Provar ponta a ponta

1. No celular, mande **/start** pro seu bot → deve chegar a mensagem de boas-vindas
   e o log registrar `subscribed ...`.
2. Como admin, mande **/now** → o digest é montado e enviado na hora
   (a 1ª vez pode vir vazio se não houver notícia nova desde o seed).
3. **/list** (admin) → mostra os inscritos.

Se isso funcionar, o serviço está de pé e agendado. Amanhã às 07:00 (fuso
`NEWS_TZ`) o broadcast sai sozinho pra todos os inscritos.

## Operação

```bash
kubectl -n news logs -f deploy/news-agent           # acompanhar
kubectl -n news rollout restart deploy/news-agent   # reiniciar
kubectl -n news set env deploy/news-agent NEWS_DIGEST_TIME=06:30   # ajuste rápido
kubectl -n news delete -k k8s/                        # remover tudo (PVC persiste dados)
```

Ajustes de conteúdo (feeds, modelo, limites): edite o ConfigMap
(`kubectl -n news edit configmap news-agent-config`) e reinicie o rollout.
Fontes RSS ficam em `app/config.py` (exige rebuild + reimport da imagem).
