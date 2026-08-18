"""Fetch real-time currency quotes for the digest header."""
import logging

import requests

log = logging.getLogger("market")

_URL = "https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL"


def _fetch():
    """Fetch raw USD/EUR quote data. Returns dict or None on failure."""
    try:
        data = requests.get(_URL, timeout=10).json()
        return {
            "usd": {"price": float(data["USDBRL"]["bid"]), "pct": float(data["USDBRL"]["pctChange"])},
            "eur": {"price": float(data["EURBRL"]["bid"]), "pct": float(data["EURBRL"]["pctChange"])},
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("could not fetch quotes: %s", exc)
        return None


def get_quotes():
    """Fetch the day's quotes once and return (telegram_text, spoken_text).

    telegram_text is formatted for display (symbols, arrows). spoken_text is
    plain-language Brazilian Portuguese meant to be narrated by TTS, without
    symbols or English-style decimal points. Returns (None, None) on failure.
    """
    data = _fetch()
    if not data:
        return None, None
    return _format_telegram(data), _format_spoken(data)


def _format_telegram(data):
    def _fmt(q):
        arrow = "▲" if q["pct"] >= 0 else "▼"
        return f"R$ {q['price']:.2f} {arrow}{abs(q['pct']):.2f}%"

    return f"\U0001f4b5 Dólar: {_fmt(data['usd'])} | Euro: {_fmt(data['eur'])}"


def _format_spoken(data):
    def _fmt(name, q):
        direction = "alta" if q["pct"] >= 0 else "queda"
        price = f"{q['price']:.2f}".replace(".", ",")
        pct = f"{abs(q['pct']):.2f}".replace(".", ",")
        return f"{name} a {price} reais, em {direction} de {pct} por cento"

    return f"{_fmt('dólar', data['usd'])}; {_fmt('euro', data['eur'])}"
