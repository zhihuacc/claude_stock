import pytest
import numpy as np
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from indicators.volume import VolumeIndicators
from indicators.support_resistance import SupportResistanceIndicators


def test_trend_sma_columns(sample_ohlcv_df, mock_config):
    calc = TrendIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    assert "SMA_20" in df.columns
    assert "SMA_50" in df.columns
    assert "SMA_200" in df.columns
    assert "EMA_9" in df.columns
    assert "MACD_LINE" in df.columns
    assert "ADX_14" in df.columns


def test_sma_warmup_nan(sample_ohlcv_df, mock_config):
    calc = TrendIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    # First 19 rows of SMA_20 should be NaN
    assert df["SMA_20"].iloc[:19].isna().all()
    # After warmup, should have values
    assert df["SMA_20"].iloc[200:].notna().all()


def test_momentum_rsi_range(sample_ohlcv_df, mock_config):
    calc = MomentumIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    assert "RSI_14" in df.columns
    valid = df["RSI_14"].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_momentum_stoch_range(sample_ohlcv_df, mock_config):
    calc = MomentumIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    assert "STOCH_K" in df.columns
    k = df["STOCH_K"].dropna()
    assert (k >= 0).all() and (k <= 100).all()


def test_volatility_bollinger_bands(sample_ohlcv_df, mock_config):
    calc = VolatilityIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    assert "BB_UPPER" in df.columns
    assert "BB_LOWER" in df.columns
    valid = df.dropna(subset=["BB_UPPER", "BB_LOWER"])
    assert (valid["BB_UPPER"] >= valid["BB_LOWER"]).all()


def test_volume_obv(sample_ohlcv_df, mock_config):
    calc = VolumeIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df, timeframe="1D")
    assert "OBV" in df.columns
    assert "VOL_RATIO" in df.columns


def test_support_resistance_pivots(sample_ohlcv_df, mock_config):
    calc = SupportResistanceIndicators(mock_config)
    df = calc.calculate(sample_ohlcv_df)
    assert "PP" in df.columns
    assert "R1" in df.columns
    assert "S1" in df.columns
    assert "HIGH_52W" in df.columns
    # 52W high must be >= all closes
    assert (df["HIGH_52W"] >= df["high"]).all()
