import pytest
from datetime import datetime
from signals.rules import (
    rule_rsi_oversold, rule_rsi_overbought,
    rule_golden_cross, rule_death_cross,
    rule_macd_bullish_crossover, rule_macd_bearish_crossover,
    rule_volume_spike, rule_bb_squeeze,
    rule_bb_breakout_upper, rule_bb_breakout_lower,
)

DT = datetime(2024, 1, 15)
SYM = "AAPL"
TF = "1D"


def test_rsi_oversold_triggers(mock_config):
    ind = {"RSI_14": 25.0}
    sig = rule_rsi_oversold(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None
    assert sig["signal_name"] == "RSI_OVERSOLD"
    assert sig["severity"] == "warning"


def test_rsi_oversold_no_trigger(mock_config):
    ind = {"RSI_14": 45.0}
    assert rule_rsi_oversold(SYM, TF, DT, ind, {}, mock_config) is None


def test_rsi_overbought_triggers(mock_config):
    ind = {"RSI_14": 75.0}
    sig = rule_rsi_overbought(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None
    assert sig["signal_name"] == "RSI_OVERBOUGHT"


def test_golden_cross_triggers(mock_config):
    cur = {"SMA_50": 201.0, "SMA_200": 200.0}
    prev = {"SMA_50": 199.0, "SMA_200": 200.0}
    sig = rule_golden_cross(SYM, TF, DT, cur, prev, mock_config)
    assert sig is not None
    assert sig["signal_name"] == "GOLDEN_CROSS"


def test_golden_cross_no_trigger_already_above(mock_config):
    # Both days fast > slow — not a crossover
    cur = {"SMA_50": 201.0, "SMA_200": 200.0}
    prev = {"SMA_50": 200.5, "SMA_200": 200.0}
    assert rule_golden_cross(SYM, TF, DT, cur, prev, mock_config) is None


def test_death_cross_triggers(mock_config):
    cur = {"SMA_50": 199.0, "SMA_200": 200.0}
    prev = {"SMA_50": 201.0, "SMA_200": 200.0}
    sig = rule_death_cross(SYM, TF, DT, cur, prev, mock_config)
    assert sig is not None
    assert sig["signal_name"] == "DEATH_CROSS"


def test_macd_bullish_triggers(mock_config):
    cur = {"MACD_LINE": 0.5, "MACD_SIGNAL": 0.3}
    prev = {"MACD_LINE": 0.2, "MACD_SIGNAL": 0.3}
    sig = rule_macd_bullish_crossover(SYM, TF, DT, cur, prev, mock_config)
    assert sig is not None


def test_volume_spike_triggers(mock_config):
    ind = {"VOL_RATIO": 3.5}
    sig = rule_volume_spike(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None
    assert sig["current_value"] == 3.5


def test_volume_spike_no_trigger(mock_config):
    ind = {"VOL_RATIO": 1.5}
    assert rule_volume_spike(SYM, TF, DT, ind, {}, mock_config) is None


def test_bb_squeeze_triggers(mock_config):
    ind = {"BB_WIDTH": 3.0, "BB_MIDDLE": 100.0}
    sig = rule_bb_squeeze(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None  # 3/100 = 0.03 < 0.05


def test_bb_breakout_upper(mock_config):
    ind = {"close": 196.0, "BB_UPPER": 195.0}
    sig = rule_bb_breakout_upper(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None


def test_bb_breakout_lower(mock_config):
    ind = {"close": 184.0, "BB_LOWER": 185.0}
    sig = rule_bb_breakout_lower(SYM, TF, DT, ind, {}, mock_config)
    assert sig is not None


def test_disabled_rule(mock_config):
    cfg = dict(mock_config)
    cfg["signals"]["rules"]["rsi_oversold"]["enabled"] = False
    assert rule_rsi_oversold(SYM, TF, DT, {"RSI_14": 25.0}, {}, cfg) is None


def test_missing_indicator_returns_none(mock_config):
    assert rule_rsi_oversold(SYM, TF, DT, {}, {}, mock_config) is None
