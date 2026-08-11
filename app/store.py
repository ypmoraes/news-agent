"""SQLite storage: dedup (`seen`), `subscribers`, and key/value `state`."""
import logging
import os
import sqlite3
import time

import config

log = logging.getLogger("store")


def open_db():
    path = config.DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, ts INTEGER);
        CREATE TABLE IF NOT EXISTS subscribers (chat_id TEXT PRIMARY KEY, name TEXT, ts INTEGER);
        CREATE TABLE IF NOT EXISTS state (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS digest_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            candidates INTEGER,
            curated INTEGER,
            subscribers INTEGER,
            has_podcast INTEGER,
            anthropic_input_tokens INTEGER DEFAULT 0,
            anthropic_output_tokens INTEGER DEFAULT 0,
            elevenlabs_chars INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()
    return conn


# --- dedup ---
def seen(conn, iid):
    return conn.execute("SELECT 1 FROM seen WHERE id = ?", (iid,)).fetchone() is not None


def mark_seen(conn, iid):
    conn.execute("INSERT OR IGNORE INTO seen (id, ts) VALUES (?, ?)", (iid, int(time.time())))


def seen_empty(conn):
    return conn.execute("SELECT 1 FROM seen LIMIT 1").fetchone() is None


# --- subscribers ---
def add_subscriber(conn, chat_id, name):
    conn.execute(
        "INSERT OR IGNORE INTO subscribers (chat_id, name, ts) VALUES (?, ?, ?)",
        (str(chat_id), name, int(time.time())),
    )
    conn.commit()


def remove_subscriber(conn, chat_id):
    conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (str(chat_id),))
    conn.commit()


def list_subscribers(conn):
    return [r[0] for r in conn.execute("SELECT chat_id FROM subscribers")]


def list_subscribers_full(conn):
    return conn.execute("SELECT chat_id, name, ts FROM subscribers ORDER BY ts").fetchall()


# --- digest log ---
def log_digest(conn, candidates, curated, subscribers, has_podcast,
               anthropic_input=0, anthropic_output=0, elevenlabs_chars=0):
    conn.execute(
        """INSERT INTO digest_log
           (ts, candidates, curated, subscribers, has_podcast,
            anthropic_input_tokens, anthropic_output_tokens, elevenlabs_chars)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (int(time.time()), candidates, curated, subscribers, int(has_podcast),
         anthropic_input, anthropic_output, elevenlabs_chars),
    )
    conn.commit()


def week_stats(conn):
    """Return stats for the last 7 days."""
    since = int(time.time()) - 7 * 86400
    row = conn.execute(
        """SELECT
            COUNT(*) as editions,
            SUM(candidates) as candidates,
            SUM(curated) as curated,
            SUM(has_podcast) as podcasts,
            SUM(anthropic_input_tokens) as input_tokens,
            SUM(anthropic_output_tokens) as output_tokens,
            SUM(elevenlabs_chars) as el_chars
           FROM digest_log WHERE ts >= ?""",
        (since,),
    ).fetchone()
    subs = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
    return {
        "editions": row[0] or 0,
        "candidates": row[1] or 0,
        "curated": row[2] or 0,
        "podcasts": row[3] or 0,
        "input_tokens": row[4] or 0,
        "output_tokens": row[5] or 0,
        "elevenlabs_chars": row[6] or 0,
        "subscribers": subs,
    }


def month_elevenlabs_chars(conn):
    """Return total ElevenLabs chars sent by the bot in the last 30 days."""
    since = int(time.time()) - 30 * 86400
    row = conn.execute(
        "SELECT SUM(elevenlabs_chars) FROM digest_log WHERE ts >= ?", (since,)
    ).fetchone()
    return row[0] or 0


# --- state ---
def get_state(conn, key):
    r = conn.execute("SELECT v FROM state WHERE k = ?", (key,)).fetchone()
    return r[0] if r else None


def set_state(conn, key, value):
    conn.execute(
        "INSERT INTO state (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
        (key, str(value)),
    )
    conn.commit()
