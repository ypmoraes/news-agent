"""Always-up bot: listens for subscribe/unsubscribe commands and broadcasts
the morning digest to all subscribers at DIGEST_TIME."""
import html
import logging
import signal
import sys
from datetime import datetime

import agent
import config
import feeds
import market
import memory
import podcast
import store
import telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("main")

_running = True

PROJECT_INFO = (
    "🛠 <b>Como o Bom Di.IA News é feito</b>\n\n"
    "Curioso sobre o que roda por trás do digest de todo dia? Aqui vai um resumo.\n\n"
    "<b>O que ele faz</b>\n"
    "Todo dia útil, o bot coleta notícias de ~11 fontes de tech e economia "
    "(Hacker News, The Verge, Ars Technica, TechCrunch, Valor, InfoMoney, "
    "Bloomberg, WSJ, FT...), descarta duplicadas e ruído, e pede pra uma IA "
    "escolher e explicar as que realmente importam. Depois narra tudo num "
    "podcast curtinho.\n\n"
    "<b>O \"cérebro\": Claude (Anthropic)</b>\n"
    "Quem cura as notícias é o Claude. Ele não só lê o título e o resumo do "
    "RSS — quando isso não é suficiente pra julgar a importância de uma "
    "notícia, ele mesmo decide buscar o artigo completo antes de decidir. "
    "Ele também escreve o roteiro do podcast em português.\n\n"
    "<b>Memória: o bot não esquece o que já contou</b>\n"
    "Antes de curar o digest de hoje, o bot consulta um banco de dados "
    "vetorial (ChromaDB) com tudo que já foi coberto nos últimos dias. Isso "
    "evita repetir a mesma notícia e ajuda a IA a enquadrar desdobramentos "
    "(\"essa é continuação daquilo de anteontem\") em vez de tratar tudo "
    "como fato isolado.\n\n"
    "<b>Voz: ElevenLabs</b>\n"
    "O roteiro escrito pelo Claude vira áudio através da ElevenLabs "
    "(text-to-speech), convertido e enviado como podcast aqui no Telegram.\n\n"
    "<b>Onde ele mora</b>\n"
    "O bot roda 24h num servidor caseiro, dentro de um "
    "cluster Kubernetes leve chamado k3s. É um processo Python único, "
    "escrito do zero: ouve seus comandos (/start, /stop etc.) e, no mesmo "
    "loop, dispara o digest sozinho no horário certo. Tudo em containers "
    "Docker, com o estado (quem é assinante, o que já foi enviado) guardado "
    "num banco de dados SQLite.\n\n"
    "<b>Como foi construído</b>\n"
    "O projeto inteiro — do bot ao deploy no Kubernetes — foi desenvolvido "
    "em pair programming com o Claude Code, o assistente de código da "
    "Anthropic: a IA que cura as notícias também ajudou a escrever o "
    "software que faz a curadoria. Sim, é IA construindo e operando IA. 🤖\n\n"
    "<b>Quem tá por trás</b>\n"
    "Quem criou esse bot foi o Yuri Moraes, DevOps Engineer. Ele começou "
    "esse side project em agosto de 2026 pra resolver um problema dele: "
    "ficar bem informado sem precisar abrir um monte de site e fonte "
    "diferente todo dia. O código tá aberto no GitHub: "
    "https://github.com/ypmoraes/news-agent\n\n"
    "<i>Perguntas ou sugestões? Responde aqui mesmo.</i>"
)


def _stop(*_):
    global _running
    _running = False
    log.info("shutdown signal received")


def _now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(config.TIMEZONE))
    except Exception:  # noqa: BLE001
        return datetime.now()


def run_digest(conn):
    candidates = feeds.collect_new(conn)
    if not candidates:
        log.info("digest: no new items")
        return
    subs = store.list_subscribers(conn)
    if not subs:
        log.info("digest: no subscribers; marking %d items seen", len(candidates))
        feeds.mark_all(conn, candidates)
        return

    memory_context = memory.find_similar(candidates)
    digest, input_tokens, output_tokens = agent.curate(candidates, memory_context)
    quotes = market.get_quotes()
    mp3, el_chars = podcast.produce(digest, quotes=quotes)
    text = telegram.format_digest(digest, candidates, has_podcast=bool(mp3), quotes=quotes)
    sent = 0
    for chat_id in subs:
        ok, code = telegram.send_long(chat_id, text)
        if not ok and code == 403:
            store.remove_subscriber(conn, chat_id)
            log.info("removed blocked subscriber %s", chat_id)
        elif ok:
            sent += 1
    feeds.mark_all(conn, candidates)
    if digest:
        memory.save_digest(digest)
    log.info("digest sent to %d/%d subscribers (%s items)",
             sent, len(subs), len(digest) if digest else "raw")

    if mp3:
        for chat_id in subs:
            telegram.send_audio(chat_id, mp3, title="Bom Di.IA News", performer="Bom Di.IA News")
        log.info("podcast sent to %d subscribers", len(subs))
    else:
        log.warning("podcast not generated; skipping")

    store.log_digest(conn,
        candidates=len(candidates),
        curated=len(digest) if digest else 0,
        subscribers=len(subs),
        has_podcast=bool(mp3),
        anthropic_input=input_tokens,
        anthropic_output=output_tokens,
        elevenlabs_chars=el_chars,
    )


def send_weekly_stats(conn):
    if not config.ADMIN_CHAT_ID:
        return
    stats = store.week_stats(conn)
    # custo estimado: Haiku = US$0.80/1M input, US$4.00/1M output
    cost_anthropic = (stats["input_tokens"] / 1_000_000 * 0.80) + (stats["output_tokens"] / 1_000_000 * 4.00)
    el_month = store.month_elevenlabs_chars(conn)

    from datetime import date, timedelta
    today = _now().date()
    week_start = (today - timedelta(days=6)).strftime("%d/%m")
    week_end = today.strftime("%d/%m")

    el_line = f"\u2022 ElevenLabs: {el_month:,} chars enviados nos \u00faltimos 30 dias"

    text = (
        f"\U0001f4ca <b>Bom Di.IA News — Stats da semana ({week_start} a {week_end})</b>\n\n"
        f"\U0001f4ec Edi\u00e7\u00f5es enviadas: {stats['editions']}\n"
        f"\U0001f465 Assinantes ativos: {stats['subscribers']}\n"
        f"\U0001f4f0 Not\u00edcias coletadas: {stats['candidates']}\n"
        f"\u2702\ufe0f Not\u00edcias curadas: {stats['curated']}\n"
        f"\U0001f3d9 Podcasts gerados: {stats['podcasts']}\n\n"
        f"\U0001f4b0 <b>Custos estimados da semana:</b>\n"
        f"\u2022 Claude (Haiku): ~US$ {cost_anthropic:.3f} "
        f"({stats['input_tokens']:,} input / {stats['output_tokens']:,} output tokens)\n"
        f"{el_line}"
    )
    telegram.send_message(config.ADMIN_CHAT_ID, text)
    log.info("weekly stats sent to admin")


def maybe_digest(conn):
    now = _now()
    if now.weekday() >= 5:  # 5=sábado, 6=domingo
        return
    if store.get_state(conn, "last_digest_date") == now.date().isoformat():
        return
    hh, mm = (int(x) for x in config.DIGEST_TIME.split(":"))
    if (now.hour, now.minute) >= (hh, mm):
        run_digest(conn)
        store.set_state(conn, "last_digest_date", now.date().isoformat())


def maybe_stats(conn):
    now = _now()
    if now.weekday() != 4:  # 4=sexta
        return
    if store.get_state(conn, "last_stats_date") == now.date().isoformat():
        return
    if (now.hour, now.minute) >= (8, 0):
        send_weekly_stats(conn)
        store.set_state(conn, "last_stats_date", now.date().isoformat())


ANNOUNCE_UPDATE_DATE = "2026-08-12"

UPDATE_ANNOUNCEMENT = (
    "📢 <b>Atualizações no Bom Di.IA News!</b>\n\n"
    "O bot ganhou funções novas por aqui. Digite /sobre pra ver todos os "
    "comandos disponíveis."
)


def maybe_announce_update(conn):
    """One-off broadcast telling subscribers about new features on ANNOUNCE_UPDATE_DATE."""
    now = _now()
    if now.date().isoformat() != ANNOUNCE_UPDATE_DATE:
        return
    if store.get_state(conn, "announced_update"):
        return
    if (now.hour, now.minute) < (9, 0):
        return
    subs = store.list_subscribers(conn)
    for chat_id in subs:
        telegram.send_message(chat_id, UPDATE_ANNOUNCEMENT)
    store.set_state(conn, "announced_update", "1")
    log.info("update announcement sent to %d subscribers", len(subs))


def handle_update(conn, upd):
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    name = chat.get("first_name") or chat.get("username") or ""
    cmd = text.split()[0].lower().split("@")[0]
    is_admin = config.ADMIN_CHAT_ID and str(chat_id) == str(config.ADMIN_CHAT_ID)

    if cmd == "/start":
        store.add_subscriber(conn, chat_id, name)
        telegram.send_message(chat_id, "\u2705 Inscrito! Voc\u00ea recebe o resumo de tech toda manh\u00e3.\n/stop pra sair \u2022 /help pra ajuda.")
        sources = "\n".join(f"\u2022 {s}" for s in config.FEEDS)
        telegram.send_message(chat_id, (
            "\u2139\ufe0f <b>Sobre o Bom Di.IA News</b>\n\n"
            "O Bom Di.IA News \u00e9 um digest di\u00e1rio de tecnologia e economia, "
            "curado por intelig\u00eancia artificial e entregue todo dia \u00e0s 7h30 da manh\u00e3 "
            "(de segunda a sexta).\n\n"
            f"<b>Fontes monitoradas:</b>\n{sources}\n\n"
            "<b>Comandos:</b>\n"
            "/start \u2014 inscrever-se\n"
            "/stop \u2014 cancelar inscri\u00e7\u00e3o\n"
            "/sobre \u2014 sobre o bot\n"
            "/projeto \u2014 como o bot \u00e9 feito por baixo do cap\u00f4\n\n"
            "Desenvolvido com Claude (Anthropic) + ElevenLabs."
        ))
        log.info("subscribed %s (%s)", chat_id, name)
    elif cmd == "/stop":
        store.remove_subscriber(conn, chat_id)
        telegram.send_message(chat_id, "Voc\u00ea saiu da lista. /start pra voltar quando quiser.")
        log.info("unsubscribed %s", chat_id)
    elif cmd == "/help":
        telegram.send_message(chat_id, "Comandos:\n/start \u2014 inscrever\n/stop \u2014 sair\n/sobre \u2014 sobre o bot\n/projeto \u2014 como o bot \u00e9 feito\n/help \u2014 esta mensagem")
    elif cmd == "/sobre":
        sources = "\n".join(f"\u2022 {s}" for s in config.FEEDS)
        telegram.send_message(chat_id, (
            "\u2139\ufe0f <b>Sobre o Bom Di.IA News</b>\n\n"
            "O Bom Di.IA News \u00e9 um digest di\u00e1rio de tecnologia e economia, "
            "curado por intelig\u00eancia artificial e entregue todo dia \u00fas 7h30 da manh\u00e3 "
            "(de segunda a sexta).\n\n"
            f"<b>Fontes monitoradas:</b>\n{sources}\n\n"
            "<b>Comandos:</b>\n"
            "/start \u2014 inscrever-se\n"
            "/stop \u2014 cancelar inscri\u00e7\u00e3o\n"
            "/sobre \u2014 esta mensagem\n"
            "/projeto \u2014 como o bot \u00e9 feito por baixo do cap\u00f4\n\n"
            "Desenvolvido com Claude (Anthropic) + ElevenLabs."
        ))
    elif cmd == "/projeto":
        telegram.send_message(chat_id, PROJECT_INFO)
    elif cmd == "/list" and is_admin:
        rows = store.list_subscribers_full(conn)
        body = "\n".join(f"\u2022 {n or '?'} ({cid})" for cid, n, ts in rows) or "(nenhum inscrito)"
        telegram.send_message(chat_id, f"<b>Inscritos ({len(rows)})</b>\n{body}")
    elif cmd == "/now" and is_admin:
        telegram.send_message(chat_id, "Disparando digest agora\u2026")
        run_digest(conn)
    elif cmd == "/stats" and is_admin:
        send_weekly_stats(conn)
    elif cmd.startswith("/"):
        telegram.send_message(chat_id, "Comando não reconhecido. /help pra lista de comandos.")
    elif not is_admin:
        forward_to_admin(chat_id, name, text)
        telegram.send_message(chat_id, "Recebido! O Yuri vê sua mensagem por aqui e pode te responder direto.")


def forward_to_admin(chat_id, name, text):
    if not config.ADMIN_CHAT_ID:
        return
    who = f"{html.escape(name)} ({chat_id})" if name else str(chat_id)
    telegram.send_message(
        config.ADMIN_CHAT_ID,
        f"📩 <b>Mensagem de {who}</b>\n\n{html.escape(text)}",
    )


def main():
    if not config.BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN required")
        sys.exit(1)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    conn = store.open_db()
    feeds.seed_if_empty(conn)
    offset = store.get_state(conn, "offset")
    offset = int(offset) if offset else None
    log.info("bot up; polling. digest at %s (%s)", config.DIGEST_TIME, config.TIMEZONE)

    while _running:
        updates = telegram.get_updates(offset, config.POLL_TIMEOUT)
        for upd in updates:
            try:
                handle_update(conn, upd)
            except Exception as exc:  # noqa: BLE001
                log.warning("update handling error: %s", exc)
            offset = upd["update_id"] + 1
        if updates:
            store.set_state(conn, "offset", offset)
        try:
            maybe_digest(conn)
        except Exception as exc:  # noqa: BLE001
            log.warning("digest error: %s", exc)
        try:
            maybe_stats(conn)
        except Exception as exc:  # noqa: BLE001
            log.warning("stats error: %s", exc)
        try:
            maybe_announce_update(conn)
        except Exception as exc:  # noqa: BLE001
            log.warning("projeto announcement error: %s", exc)

    conn.close()
    log.info("stopped cleanly")


if __name__ == "__main__":
    main()
