import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from .models import OHLCV, Indicator, Signal, WatchlistEntry, FetchLog, get_engine, init_db

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = get_engine(db_path)
        init_db(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def close(self):
        self.engine.dispose()

    # ── OHLCV ─────────────────────────────────────────────────────────────────

    def upsert_ohlcv(self, records: list[dict]) -> int:
        if not records:
            return 0
        sql = text("""
            INSERT OR REPLACE INTO ohlcv
                (symbol, timeframe, datetime, open, high, low, close, volume, adjusted_close,
                 created_at, updated_at)
            VALUES
                (:symbol, :timeframe, :datetime, :open, :high, :low, :close, :volume,
                 :adjusted_close, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        # Ensure adjusted_close key present in every record
        normalised = []
        for r in records:
            row = dict(r)
            row.setdefault("adjusted_close", None)
            normalised.append(row)
        with self.Session() as session:
            result = session.execute(sql, normalised)
            session.commit()
            return result.rowcount

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> pd.DataFrame:
        conditions = ["symbol = :symbol", "timeframe = :timeframe"]
        params: dict = {"symbol": symbol, "timeframe": timeframe}

        if start_dt is not None:
            conditions.append("datetime >= :start_dt")
            params["start_dt"] = start_dt
        if end_dt is not None:
            conditions.append("datetime <= :end_dt")
            params["end_dt"] = end_dt

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT datetime, open, high, low, close, volume, adjusted_close
            FROM ohlcv
            WHERE {where_clause}
            ORDER BY datetime DESC
            LIMIT {limit if limit is not None else -1}
            OFFSET {offset}
        """
        with self.Session() as session:
            result = session.execute(text(query), params)
            rows = result.fetchall()
            columns = result.keys()

        df = pd.DataFrame(rows, columns=list(columns))
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"])
        return df

    # ── Indicators ────────────────────────────────────────────────────────────

    def upsert_indicators(self, records: list[dict]) -> int:
        if not records:
            return 0
        sql = text("""
            INSERT OR REPLACE INTO indicators
                (symbol, timeframe, datetime, indicator_name, value, created_at)
            VALUES
                (:symbol, :timeframe, :datetime, :indicator_name, :value, CURRENT_TIMESTAMP)
        """)
        with self.Session() as session:
            result = session.execute(sql, records)
            session.commit()
            return result.rowcount

    def get_indicators(
        self,
        symbol: str,
        timeframe: str,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        names: Optional[list[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> pd.DataFrame:
        conditions = ["symbol = :symbol", "timeframe = :timeframe"]
        params: dict = {"symbol": symbol, "timeframe": timeframe}

        if start_dt is not None:
            conditions.append("datetime >= :start_dt")
            params["start_dt"] = start_dt
        if end_dt is not None:
            conditions.append("datetime <= :end_dt")
            params["end_dt"] = end_dt
        if names:
            placeholders = ", ".join(f":name_{i}" for i in range(len(names)))
            conditions.append(f"indicator_name IN ({placeholders})")
            for i, n in enumerate(names):
                params[f"name_{i}"] = n

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT datetime, indicator_name, value
            FROM indicators
            WHERE {where_clause}
            ORDER BY datetime DESC
            LIMIT {limit if limit is not None else -1}
            OFFSET {offset}
        """
        with self.Session() as session:
            result = session.execute(text(query), params)
            rows = result.fetchall()

        if not rows:
            return pd.DataFrame()

        df_raw = pd.DataFrame(rows, columns=["datetime", "indicator_name", "value"])
        df_raw["datetime"] = pd.to_datetime(df_raw["datetime"])

        # Pivot: each indicator_name becomes a column, indexed by datetime
        df_pivot = df_raw.pivot_table(
            index="datetime", columns="indicator_name", values="value", aggfunc="first"
        )
        df_pivot.columns.name = None
        df_pivot = df_pivot.sort_index(ascending=False)
        return df_pivot

    # ── Signals ───────────────────────────────────────────────────────────────

    def upsert_signals(self, records: list[dict]) -> int:
        if not records:
            return 0
        sql = text("""
            INSERT OR REPLACE INTO signals
                (symbol, signal_name, timeframe, datetime, current_value, threshold,
                 severity, message, acknowledged, created_at)
            VALUES
                (:symbol, :signal_name, :timeframe, :datetime, :current_value, :threshold,
                 :severity, :message, :acknowledged, CURRENT_TIMESTAMP)
        """)
        normalised = []
        for r in records:
            row = dict(r)
            row.setdefault("current_value", None)
            row.setdefault("threshold", None)
            row.setdefault("message", None)
            row.setdefault("acknowledged", 0)
            normalised.append(row)
        with self.Session() as session:
            result = session.execute(sql, normalised)
            session.commit()
            return result.rowcount

    def get_signals(
        self,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        severity: Optional[str] = None,
        symbols: Optional[list[str]] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict]:
        conditions: list[str] = []
        params: dict = {}

        if start_dt is not None:
            conditions.append("datetime >= :start_dt")
            params["start_dt"] = start_dt
        if end_dt is not None:
            conditions.append("datetime <= :end_dt")
            params["end_dt"] = end_dt
        if severity is not None:
            conditions.append("severity = :severity")
            params["severity"] = severity
        if symbols:
            placeholders = ", ".join(f":sym_{i}" for i in range(len(symbols)))
            conditions.append(f"symbol IN ({placeholders})")
            for i, s in enumerate(symbols):
                params[f"sym_{i}"] = s
        if timeframe is not None:
            conditions.append("timeframe = :timeframe")
            params["timeframe"] = timeframe

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT id, symbol, signal_name, timeframe, datetime, current_value, threshold,
                   severity, message, acknowledged, created_at
            FROM signals
            {where_clause}
            ORDER BY datetime DESC
            LIMIT {limit if limit is not None else -1}
            OFFSET {offset}
        """
        with self.Session() as session:
            result = session.execute(text(query), params)
            rows = result.fetchall()
            keys = list(result.keys())

        return [dict(zip(keys, row)) for row in rows]

    # ── Fetch Log ─────────────────────────────────────────────────────────────

    def get_last_fetch_datetime(self, symbol: str, timeframe: str) -> Optional[datetime]:
        sql = text("""
            SELECT last_datetime FROM fetch_log
            WHERE symbol = :symbol AND timeframe = :timeframe
        """)
        with self.Session() as session:
            result = session.execute(sql, {"symbol": symbol, "timeframe": timeframe})
            row = result.fetchone()
        if row is None:
            return None
        last_dt = row[0]
        if isinstance(last_dt, str):
            return datetime.fromisoformat(last_dt)
        return last_dt

    def update_fetch_log(self, symbol: str, timeframe: str, last_datetime: datetime):
        sql = text("""
            INSERT OR REPLACE INTO fetch_log (symbol, timeframe, last_datetime, fetched_at)
            VALUES (:symbol, :timeframe, :last_datetime, CURRENT_TIMESTAMP)
        """)
        with self.Session() as session:
            session.execute(sql, {
                "symbol": symbol,
                "timeframe": timeframe,
                "last_datetime": last_datetime,
            })
            session.commit()

    # ── Watchlist Status ──────────────────────────────────────────────────────

    def get_watchlist_status(self) -> list[dict]:
        """Return a list of dicts summarising each symbol+timeframe in fetch_log."""
        fl_sql = text("SELECT symbol, timeframe, last_datetime, fetched_at FROM fetch_log")
        wl_sql = text("SELECT symbol, name, sector FROM watchlist")
        with self.Session() as session:
            fl_rows = session.execute(fl_sql).fetchall()
            wl_rows = session.execute(wl_sql).fetchall()

        wl_map = {r[0]: {"name": r[1], "sector": r[2]} for r in wl_rows}

        results = []
        for symbol, timeframe, last_datetime, fetched_at in fl_rows:
            # OHLCV row count for this symbol+timeframe
            with self.Session() as session:
                count_result = session.execute(
                    text("SELECT COUNT(*) FROM ohlcv WHERE symbol = :s AND timeframe = :t"),
                    {"s": symbol, "t": timeframe},
                )
                ohlcv_count = count_result.scalar()

                # Most recent signal
                sig_result = session.execute(
                    text("""
                        SELECT signal_name, severity, datetime, message
                        FROM signals
                        WHERE symbol = :s AND timeframe = :t
                        ORDER BY datetime DESC
                        LIMIT 1
                    """),
                    {"s": symbol, "t": timeframe},
                )
                sig_row = sig_result.fetchone()

            entry = {
                "symbol": symbol,
                "timeframe": timeframe,
                "name": wl_map.get(symbol, {}).get("name"),
                "sector": wl_map.get(symbol, {}).get("sector"),
                "last_datetime": last_datetime,
                "fetched_at": fetched_at,
                "ohlcv_count": ohlcv_count,
                "last_signal_name": sig_row[0] if sig_row else None,
                "last_signal_severity": sig_row[1] if sig_row else None,
                "last_signal_datetime": sig_row[2] if sig_row else None,
                "last_signal_message": sig_row[3] if sig_row else None,
            }
            results.append(entry)

        return results

    def get_all_indicator_names(self, symbol: str, timeframe: str) -> list[str]:
        sql = text("""
            SELECT DISTINCT indicator_name
            FROM indicators
            WHERE symbol = :symbol AND timeframe = :timeframe
            ORDER BY indicator_name
        """)
        with self.Session() as session:
            result = session.execute(sql, {"symbol": symbol, "timeframe": timeframe})
            rows = result.fetchall()
        return [row[0] for row in rows]
