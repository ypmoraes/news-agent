"""Fetch real-time currency quotes for the digest header."""
import logging

import requests

log = logging.getLogger("market")

_URL = "https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL"


def get_quotes():
    """Return formatted currency string or None on failure."""
    try:
        data = requests.get(_URL, timeout=10).json()

        usd = data["USDBRL"]
        eur = data["EURBRL"]

        def _fmt(q):
            price = float(q["bid"])
            pct = float(q["pctChange"])
            arrow = "▲" if pct >= 0 else "▼"
            return f"R$ {price:.2f} {arrow}{abs(pct):.2f}%"

        return f"\U0001f4b5 D\u00f3lar: {_fmt(usd)} | Euro: {_fmt(eur)}"
    except Exception as exc:  # noqa: BLE001
        log.warning("could not fetch quotes: %s", exc)
        return None
