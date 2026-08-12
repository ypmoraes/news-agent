"""Battery/AC monitoring for the laptop-server: alerts the admin via Telegram
if it's running unplugged and the charge drops below a threshold.

Reads straight from node-exporter's /metrics (Prometheus text format) instead
of adding a metrics-parsing dependency for two numbers.
"""
import logging
import re
import time

import requests

import config
import store
import telegram

log = logging.getLogger("battery")

_CAPACITY_RE = re.compile(r'node_power_supply_capacity\{power_supply="BAT0"\}\s+([\d.]+)')
_ONLINE_RE = re.compile(r'node_power_supply_online\{power_supply="AC"\}\s+([\d.]+)')


def _read():
    """Return (capacity_pct, ac_online) or (None, None) on failure."""
    try:
        resp = requests.get(config.BATTERY_CHECK_URL, timeout=10)
        resp.raise_for_status()
        cap_match = _CAPACITY_RE.search(resp.text)
        ac_match = _ONLINE_RE.search(resp.text)
        if not cap_match or not ac_match:
            return None, None
        return float(cap_match.group(1)), ac_match.group(1) == "1"
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read battery metrics: %s", exc)
        return None, None


def status_text():
    """Return a PT-BR one-liner with the current battery/AC status, for /bateria."""
    capacity, ac_online = _read()
    if capacity is None:
        return "\U0001f50b Não consegui ler o status da bateria agora."
    fonte = "\U0001f50c na tomada" if ac_online else "\U0001f50b na bateria"
    return f"\U0001f50b {capacity:.0f}% — {fonte}"


def _check_ac_transition(conn, ac_online, capacity):
    """Alert when AC power is unplugged or reconnected (edge-triggered, not level).

    Skips the very first read after startup (no previous state to compare
    against) so a pod restart while already unplugged doesn't fire a false alert.
    """
    prev = store.get_state(conn, "battery_ac_online")
    current = "1" if ac_online else "0"
    if prev is not None and prev != current:
        if current == "0":
            telegram.send_message(
                config.ADMIN_CHAT_ID,
                "\U0001f50c❌ <b>Servidor desconectado da tomada!</b>\n\n"
                f"Rodando na bateria, {capacity:.0f}% de carga.",
            )
            log.warning("AC unplugged, running on battery at %.0f%%", capacity)
        else:
            telegram.send_message(config.ADMIN_CHAT_ID, "\U0001f50c✅ Servidor reconectado à tomada.")
            log.info("AC reconnected")
    store.set_state(conn, "battery_ac_online", current)


def _check_low_battery(conn, ac_online, capacity):
    low = (not ac_online) and capacity < config.BATTERY_ALERT_THRESHOLD
    already_sent = store.get_state(conn, "battery_alert_sent") == "1"

    if low and not already_sent:
        telegram.send_message(
            config.ADMIN_CHAT_ID,
            "\U0001f50b <b>Bateria baixa no servidor!</b>\n\n"
            f"{capacity:.0f}% e desconectado da tomada. "
            "O bot (e tudo mais no cluster) pode cair se a bateria acabar.",
        )
        store.set_state(conn, "battery_alert_sent", "1")
        log.warning("low battery alert sent: %.0f%% unplugged", capacity)
    elif not low and already_sent:
        store.set_state(conn, "battery_alert_sent", "0")


def maybe_alert(conn):
    if not config.BATTERY_ALERT_ENABLED or not config.ADMIN_CHAT_ID:
        return

    now = int(time.time())
    last_check = store.get_state(conn, "battery_last_check")
    if last_check and now - int(last_check) < config.BATTERY_CHECK_INTERVAL_MIN * 60:
        return
    store.set_state(conn, "battery_last_check", now)

    capacity, ac_online = _read()
    if capacity is None:
        return

    _check_ac_transition(conn, ac_online, capacity)
    _check_low_battery(conn, ac_online, capacity)
