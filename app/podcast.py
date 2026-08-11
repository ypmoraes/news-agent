"""Podcast generation: script (via Claude) + TTS (via ElevenLabs) + OGG conversion."""
import io
import logging
from datetime import datetime

import requests

import config

log = logging.getLogger("podcast")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def generate_script(digest, quotes=None):
    """Use Claude to write a formal podcast script from the digest."""
    if not config.ANTHROPIC_API_KEY:
        return None

    items_text = "\n".join(
        f"{i}. [{d['source']}] {d['title']} — {d.get('why', '')} (link disponível no Telegram)"
        for i, d in enumerate(digest, 1)
    )

    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo(config.TIMEZONE))
    except Exception:  # noqa: BLE001
        today = datetime.now()
    today_str = today.strftime("%-d de %B de %Y").lower()
    today_str = today_str[0].upper() + today_str[1:]

    quotes_instruction = (
        f"Logo após a saudação, informe as cotações do dia: {quotes}. "
        if quotes else ""
    )

    prompt = (
        "Escreva um roteiro de podcast jornalístico formal em português brasileiro, "
        "com duração aproximada de 4 a 6 minutos (cerca de 600 a 700 palavras). "
        "Estrutura obrigatória:\n"
        f"1. Introdução: abra com 'Bom Dia News - seu podcast diário de tecnologia e economia', saudação formal e informe que hoje é {today_str}. "
        f"{quotes_instruction}\n"
        "2. Cobertura de cada notícia: mencione a fonte e o título, explique por que importa. "
        "Não mencione links durante a cobertura.\n"
        "3. Encerramento: informe que todas as notícias citadas estão disponíveis com fonte e link "
        "na mensagem do Telegram para quem quiser se aprofundar. "
        "Finalize dizendo que o Bom Dia News é publicado todos os dias às 7h30 da manhã.\n\n"
        f"Notícias do dia:\n{items_text}\n\n"
        "Retorne apenas o texto do roteiro, sem marcações, sem títulos de seção, "
        "pronto para ser narrado."
    )

    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": config.MODEL,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    except Exception as exc:  # noqa: BLE001
        log.warning("script generation failed: %s", exc)
        return None


def synthesize(script):
    """Send script to ElevenLabs, return MP3 bytes."""
    if not config.ELEVENLABS_API_KEY or not config.ELEVENLABS_VOICE_ID:
        log.warning("ElevenLabs not configured")
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "content-type": "application/json",
    }
    body = {
        "text": script,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:  # noqa: BLE001
        log.warning("ElevenLabs synthesis failed: %s", exc)
        return None


def convert_to_ogg(mp3_bytes):
    """Convert MP3 bytes to OGG/Opus bytes for Telegram sendVoice."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        ogg_buffer = io.BytesIO()
        audio.export(ogg_buffer, format="ogg", codec="libopus")
        return ogg_buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.warning("audio conversion failed: %s", exc)
        return None


def get_usage():
    """Fetch real character usage from ElevenLabs subscription API.

    Returns (used, limit) or (None, None) on failure.
    """
    if not config.ELEVENLABS_API_KEY:
        return None, None
    try:
        resp = requests.get(
            "https://api.elevenlabs.io/v1/user",
            headers={
                "xi-api-key": config.ELEVENLABS_API_KEY,
                "Authorization": f"Bearer {config.ELEVENLABS_API_KEY}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        sub = data.get("subscription", data)
        return sub.get("character_count"), sub.get("character_limit")
    except Exception as exc:  # noqa: BLE001
        log.warning("ElevenLabs usage fetch failed: %s", exc)
        return None, None


def produce(digest, quotes=None):
    """Full pipeline: digest -> script -> MP3. Returns (mp3_bytes, elevenlabs_chars) or (None, 0)."""
    if not digest:
        return None, 0

    log.info("generating podcast script")
    script = generate_script(digest, quotes=quotes)
    if not script:
        return None, 0
    log.info("script generated (%d chars)", len(script))

    log.info("synthesizing audio")
    mp3 = synthesize(script)
    if not mp3:
        return None, 0
    log.info("audio synthesized (%d bytes)", len(mp3))

    return mp3, len(script)
