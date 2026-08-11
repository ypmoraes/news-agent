#!/usr/bin/env bash
# Deploy do news-agent para o servidor k3s.
# Uso: ./deploy.sh
set -euo pipefail

SERVER="ymoraes@192.168.68.115"
SSH="ssh -i ~/.ssh/news-agent"
SCP="scp -i ~/.ssh/news-agent"
REMOTE_DIR="/opt/news-agent/news-agent"

echo "==> Copiando arquivos para o servidor..."
rsync -az --info=progress2 \
  -e "ssh -i ~/.ssh/news-agent" \
  app requirements.txt Dockerfile k8s \
  "$SERVER:$REMOTE_DIR/" \
  --exclude="*.pyc" --exclude="__pycache__"

echo "==> Build da imagem Docker..."
$SSH $SERVER "cd $REMOTE_DIR && docker build -t news-agent:latest ."

echo "==> Exportando e importando no k3s..."
$SSH $SERVER "
  docker save news-agent:latest -o /tmp/news-agent.tar &&
  sudo k3s ctr images import /tmp/news-agent.tar &&
  rm /tmp/news-agent.tar
"

echo "==> Aplicando manifests e reiniciando..."
$SSH $SERVER "
  export KUBECONFIG=~/.kube/config &&
  kubectl apply -k $REMOTE_DIR/k8s/ &&
  kubectl rollout restart deployment/news-agent -n news &&
  kubectl rollout status deployment/news-agent -n news
"

echo ""
echo "==> Deploy concluido! Logs:"
$SSH $SERVER "export KUBECONFIG=~/.kube/config && kubectl logs -n news deploy/news-agent --tail=10"
