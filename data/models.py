from datetime import datetime as _datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class OHLCV(Base):
    __tablename__ = "ohlcv"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)  # '1H','1D','1W','1M'
    datetime = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    adjusted_close = Column(Float)
    created_at = Column(DateTime, default=_datetime.utcnow)
    updated_at = Column(DateTime, default=_datetime.utcnow, onupdate=_datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "datetime"),
        Index("idx_ohlcv_symbol_timeframe_datetime", "symbol", "timeframe", "datetime"),
    )


class Indicator(Base):
    __tablename__ = "indicators"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    datetime = Column(DateTime, nullable=False)
    indicator_name = Column(String, nullable=False)
    value = Column(Float)
    created_at = Column(DateTime, default=_datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "datetime", "indicator_name"),
        Index("idx_indicators_symbol_timeframe", "symbol", "timeframe", "datetime"),
    )


class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    signal_name = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    datetime = Column(DateTime, nullable=False)
    current_value = Column(Float)
    threshold = Column(Float)
    severity = Column(String, nullable=False)
    message = Column(String)
    acknowledged = Column(Integer, default=0)
    created_at = Column(DateTime, default=_datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("symbol", "signal_name", "timeframe", "datetime"),
        Index("idx_signals_datetime", "datetime"),
        Index("idx_signals_severity", "severity"),
    )


class WatchlistEntry(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True)
    name = Column(String)
    sector = Column(String)
    active = Column(Integer, default=1)
    added_at = Column(DateTime, default=_datetime.utcnow)


class FetchLog(Base):
    __tablename__ = "fetch_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    last_datetime = Column(DateTime, nullable=False)
    fetched_at = Column(DateTime, default=_datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe"),
    )


def get_engine(db_path: str):
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(engine):
    Base.metadata.create_all(engine)
