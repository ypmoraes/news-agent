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
