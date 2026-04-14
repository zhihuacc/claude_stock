import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from .storage import StorageManager

logger = logging.getLogger(__name__)


def load_watchlist_from_config(config: dict) -> list[dict]:
    """Return the watchlist list from the config dict."""
    return config.get("watchlist", [])


def sync_watchlist_to_db(storage: StorageManager, config: dict):
    """
    Sync watchlist entries from config into the database.
    New symbols are inserted; existing symbols have their name and sector updated
    but remain active.
    """
    entries = load_watchlist_from_config(config)
    if not entries:
        logger.warning("No watchlist entries found in config.")
        return

    sql = text("""
        INSERT INTO watchlist (symbol, name, sector, active, added_at)
        VALUES (:symbol, :name, :sector, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
            name   = excluded.name,
            sector = excluded.sector
    """)
    with storage.Session() as session:
        for entry in entries:
            session.execute(sql, {
                "symbol": entry.get("symbol"),
                "name": entry.get("name"),
                "sector": entry.get("sector"),
            })
        session.commit()
    logger.info(f"Synced {len(entries)} watchlist entries to database.")


def add_symbol(
    storage: StorageManager,
    symbol: str,
    name: Optional[str] = None,
    sector: Optional[str] = None,
):
    """Insert a new symbol into the watchlist (or re-activate if already present)."""
    sql = text("""
        INSERT INTO watchlist (symbol, name, sector, active, added_at)
        VALUES (:symbol, :name, :sector, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
            name   = excluded.name,
            sector = excluded.sector,
            active = 1
    """)
    with storage.Session() as session:
        session.execute(sql, {"symbol": symbol, "name": name, "sector": sector})
        session.commit()
    logger.info(f"Added symbol {symbol} to watchlist.")


def remove_symbol(storage: StorageManager, symbol: str):
    """Soft-delete a symbol by setting active=0."""
    sql = text("UPDATE watchlist SET active = 0 WHERE symbol = :symbol")
    with storage.Session() as session:
        session.execute(sql, {"symbol": symbol})
        session.commit()
    logger.info(f"Removed symbol {symbol} from watchlist (soft delete).")


def list_symbols(storage: StorageManager, active_only: bool = True) -> list[dict]:
    """Return watchlist entries as a list of dicts."""
    if active_only:
        sql = text("""
            SELECT id, symbol, name, sector, active, added_at
            FROM watchlist
            WHERE active = 1
            ORDER BY symbol
        """)
    else:
        sql = text("""
            SELECT id, symbol, name, sector, active, added_at
            FROM watchlist
            ORDER BY symbol
        """)
    with storage.Session() as session:
        result = session.execute(sql)
        rows = result.fetchall()
        keys = list(result.keys())
    return [dict(zip(keys, row)) for row in rows]
