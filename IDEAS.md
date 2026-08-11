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
- **Grafana + Prometheus** — dashboards de métricas do cluster e do bot (CPU, memória, digests enviados). Bom para aprender Services e Ingress no k3s.
- **Loki** — agregador de logs com interface gráfica, substitui `kubectl logs`.
- **Redis** — substituir SQLite para dedup e estado, permitindo escalar para múltiplas réplicas no futuro.

## Operacional
- **Health check via Telegram** — o admin recebe um alerta se o bot ficou mudo por mais de 24h
- **`/stats`** — quantas notícias coletadas, quantas curadas, quantas enviadas nos últimos 7 dias
