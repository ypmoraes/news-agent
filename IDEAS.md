# Ideias para o news-agent

## Curadoria e conteúdo
- **Resumo em tópicos** — em vez de "why it matters" numa frase, o agent gera 3 bullet points por notícia
- **Score de relevância** — o agent atribui uma nota 1-10 e o digest mostra só acima de um limiar configurável
- **Destaque da semana** — às sextas, digest especial com as 3 maiores histórias da semana
- **Trending topics** — identificar temas que aparecem em múltiplas fontes e agrupá-los

## Personalização
- **Perfis de assinante** — cada usuário define seus interesses no `/start` e recebe um digest filtrado pra ele
- **`/feedback`** — o usuário reage a cada notícia (👍/👎) e o agent aprende o que ele gosta ao longo do tempo
- **Horário por usuário** — cada inscrito define o horário que prefere receber

## Novas fontes
- **Reddit** — subreddits como r/sysadmin, r/devops, r/brasil via RSS
- **GitHub Trending** — repositórios em alta do dia via API do GitHub
- **Blogs técnicos** — feeds do Martin Fowler, Netflix Tech Blog, AWS Blog etc.

## Formato de entrega
- **Áudio** — gerar áudio com TTS (OpenAI TTS ~US$0,015/digest ou ElevenLabs free tier) e mandar como voice message (`sendVoice`) no Telegram. Requer conversão para OGG/Opus via ffmpeg e instalação no Dockerfile. TTS não consome tokens da Anthropic.
- **Thread formatada** — cada notícia como uma mensagem separada com botão "Ler mais"
- **Modo silencioso** — envia sem notificação sonora pra não acordar quem recebe às 07:00
- **Podcast em blocos (tech / economia)** — hoje o roteiro do `podcast.py` mistura tudo numa lista única, porque o `digest` retornado pelo `agent.py` não marca a categoria de cada notícia (só pede pra "balancear" tech e economia na escolha). Precisa de um campo novo `"category": "tech"|"economia"` no JSON que o agent já retorna (mesma chamada, sem custo extra) — inferir pela fonte (ex: "Bloomberg = economia") seria frágil, porque fontes como WSJ/Bloomberg cobrem os dois temas. Com a categoria marcada, o `podcast.py` agrupa os itens e estrutura o roteiro em dois blocos com transição ("bloco 1: tecnologia... bloco 2: economia..."). Dá pra aplicar a mesma separação no texto do digest do Telegram (`telegram.format_digest`), com cabeçalho por seção.

## RAG — Memória histórica do digest
- **Problema:** o agent não tem memória entre edições — mesma notícia pode aparecer em dias seguidos e não há contexto de desdobramentos.
- **Solução:** banco vetorial (ChromaDB, arquivo local) armazena cada notícia enviada. Antes de curar, busca notícias semanticamente similares dos últimos 7 dias e passa como contexto ao Claude.
- **Exemplo:** candidata "OpenAI lança GPT-5" → banco retorna "OpenAI anuncia novo modelo" (enviada há 2 dias) → agent decide cobrir como desdobramento ou pular.
- **O que muda:** `chromadb` + `sentence-transformers` no requirements, novo `app/memory.py`, contexto histórico no prompt do `agent.py`, imagem Docker maior (~500MB a mais).
- **Quando implementar:** faz mais sentido com semanas de histórico acumulado. Adiar até o bot ter volume real de edições.

## Publicação automática do podcast (Spotify / YouTube Music)
- **Fluxo:** após gerar o MP3, fazer upload no Azure Blob Storage (URL pública HTTPS) → atualizar `feed.xml` com `feedgen` (iTunes namespaces obrigatórios) → Spotify e YouTube Music puxam o feed automaticamente.
- **Infraestrutura:** Azure Blob Storage com container público `podcast`. URL base: `https://<account>.blob.core.windows.net/podcast/`. Sem DNS próprio por enquanto.
- **Capa:** imagem 1400x1400px JPEG já disponível — fazer upload como `cover.jpg` no Blob.
- **Novo módulo:** `app/publisher.py` com `upload_episode(mp3_bytes)` e `update_feed(episode)`.
- **Dependências novas:** `feedgen`, `azure-storage-blob`.
- **Config:** `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CONTAINER_NAME`, `PODCAST_FEED_URL` no secret do k8s.
- **Submissão:** feita uma vez manualmente no Spotify for Creators e YouTube Music após feed validado em podba.se.

## Vídeo / Shorts
- **Vídeo simples com ffmpeg** — Claude escolhe notícia top, ElevenLabs gera áudio, ffmpeg combina imagem de fundo + áudio + legenda em MP4 vertical (9:16). Já temos ffmpeg no container. Baixa complexidade.
- **Avatar com D-ID** — foto (sua ou personagem IA) + áudio MP3 do ElevenLabs → D-ID devolve MP4 com avatar falando sincronizado. ~US$ 0,06/vídeo. API simples. Fluxo: digest → ElevenLabs → D-ID → MP4. Outras opções: HeyGen (~US$24/mês), Synthesia (~US$18/mês), Runway (~US$12/mês).
- **Postagem automática** — requer aprovação das APIs do YouTube Shorts, Instagram Reels ou TikTok. Cada plataforma tem seu processo.

## Infra / DevOps
- **CronJob Kubernetes** — mover o scheduler do digest para um CronJob nativo do k8s, separando responsabilidades: bot só faz polling, CronJob dispara o digest. Horário UTC: 10:30 (= 07:30 BRT). Monta o mesmo PVC do bot.
- **Perfis personalizados por assinante** — digest e podcast gerados por usuário com base nos interesses cadastrados no `/start`. Multiplica custo de Claude e ElevenLabs por assinante — adiar até ter demanda real.
- **Grafana + Prometheus** ✅ *(feito em 2026-08-12)* — dashboards de CPU/memória/disco do node e status de pods/deployments via node-exporter + kube-state-metrics + Prometheus + Grafana, manifestos em `k8s-monitoring/`. Falta: métricas de negócio do bot (custo Anthropic/ElevenLabs, edições enviadas) e Ingress/TLS (hoje é NodePort puro).
- **Prompt caching no agent de curadoria** — o loop de tool-use em `curate()` (`agent.py`) reenvia o system prompt inteiro + o histórico crescente a cada uma das até 8 rodadas de uma mesma curadoria. Marcando `cache_control: {"type": "ephemeral"}` no system prompt e nas tools, a partir da 2ª rodada esse prefixo repetido é lido a ~10% do preço de input em vez de preço cheio — só o `tool_result` novo de cada rodada (o artigo recém-buscado) continua a preço cheio. TTL padrão de 5min cobre folgado as poucas rodadas de uma curadoria; não ajuda entre digests de dias diferentes (rodam 1x/dia, cache expira antes do próximo).
- **Validação da resposta do agent com Pydantic** — hoje `agent.py` confia que o JSON devolvido pelo Claude tem sempre o formato esperado (`_parse()` só faz `json.loads` + `.get("digest", [])`, sem checar campos). Se o modelo devolver algo incompleto ou malformado, o erro só aparece depois, em outro módulo, sem indicar a causa. Pydantic permite declarar o formato esperado de cada notícia (título, fonte, url, "why", etc.) e validar a resposta assim que ela chega, com mensagem de erro clara apontando o campo problemático.
- **CI/CD com GitHub Actions self-hosted runner** — hoje o deploy é manual via `ops/deploy.sh` (rsync + ssh pro servidor). Instalando um runner self-hosted do GitHub Actions na própria máquina do k3s, um push/merge na `main` dispara o workflow automaticamente. Como o runner já roda na mesma máquina do cluster, o fluxo fica mais simples que o script atual: não precisa mais de `rsync`/`ssh` pra outro host, só `docker build` + `docker save` + `k3s ctr images import` + `kubectl apply -k k8s/` direto. Requer usuário do runner no grupo `docker` e sudo sem senha pra `k3s ctr images import`. Ponto de atenção: qualquer coisa commitada em `.github/workflows/` roda automaticamente com esses privilégios — ok num repo privado com push só do Yuri, mas vale ter em mente. Preferível a subir um Jenkins: mais leve (não é JVM) e não exige manter mais um serviço de pé no laptop-servidor.
- **Loki** — agregador de logs com interface gráfica, substitui `kubectl logs`.
- **Redis** — substituir SQLite para dedup e estado, permitindo escalar para múltiplas réplicas no futuro.

## Operacional
- **Health check via Telegram** — o admin recebe um alerta se o bot ficou mudo por mais de 24h
- **`/stats`** — quantas notícias coletadas, quantas curadas, quantas enviadas nos últimos 7 dias
