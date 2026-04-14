import math
from datetime import datetime
from typing import Optional


def _make_signal(symbol, signal_name, timeframe, dt, current_value, threshold, severity, message) -> dict:
    return {
        "symbol": symbol,
        "signal_name": signal_name,
        "timeframe": timeframe,
        "datetime": dt,
        "current_value": current_value,
        "threshold": threshold,
        "severity": severity,
        "message": message,
    }


def _valid(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def rule_rsi_oversold(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("rsi_oversold", {})
    if not cfg.get("enabled", True): return None
    rsi = ind.get("RSI_14")
    if not _valid(rsi): return None
    threshold = cfg.get("threshold", 30)
    if rsi < threshold:
        return _make_signal(symbol, "RSI_OVERSOLD", timeframe, dt, round(rsi, 2), threshold,
                            cfg.get("severity", "warning"),
                            f"{symbol} RSI={rsi:.1f} below oversold threshold {threshold} on {timeframe}")
    return None


def rule_rsi_overbought(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("rsi_overbought", {})
    if not cfg.get("enabled", True): return None
    rsi = ind.get("RSI_14")
    if not _valid(rsi): return None
    threshold = cfg.get("threshold", 70)
    if rsi > threshold:
        return _make_signal(symbol, "RSI_OVERBOUGHT", timeframe, dt, round(rsi, 2), threshold,
                            cfg.get("severity", "warning"),
                            f"{symbol} RSI={rsi:.1f} above overbought threshold {threshold} on {timeframe}")
    return None


def rule_golden_cross(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("golden_cross", {})
    if not cfg.get("enabled", True): return None
    fast_p = cfg.get("fast_period", 50)
    slow_p = cfg.get("slow_period", 200)
    fast_key = f"SMA_{fast_p}"
    slow_key = f"SMA_{slow_p}"
    cur_fast, cur_slow = ind.get(fast_key), ind.get(slow_key)
    prev_fast, prev_slow = prev_ind.get(fast_key), prev_ind.get(slow_key)
    if not all(_valid(v) for v in [cur_fast, cur_slow, prev_fast, prev_slow]): return None
    if cur_fast > cur_slow and prev_fast <= prev_slow:
        return _make_signal(symbol, "GOLDEN_CROSS", timeframe, dt, round(cur_fast, 2), round(cur_slow, 2),
                            cfg.get("severity", "alert"),
                            f"{symbol} Golden Cross: SMA{fast_p}={cur_fast:.2f} crossed above SMA{slow_p}={cur_slow:.2f} on {timeframe}")
    return None


def rule_death_cross(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("death_cross", {})
    if not cfg.get("enabled", True): return None
    fast_p = cfg.get("fast_period", 50)
    slow_p = cfg.get("slow_period", 200)
    fast_key = f"SMA_{fast_p}"
    slow_key = f"SMA_{slow_p}"
    cur_fast, cur_slow = ind.get(fast_key), ind.get(slow_key)
    prev_fast, prev_slow = prev_ind.get(fast_key), prev_ind.get(slow_key)
    if not all(_valid(v) for v in [cur_fast, cur_slow, prev_fast, prev_slow]): return None
    if cur_fast < cur_slow and prev_fast >= prev_slow:
        return _make_signal(symbol, "DEATH_CROSS", timeframe, dt, round(cur_fast, 2), round(cur_slow, 2),
                            cfg.get("severity", "alert"),
                            f"{symbol} Death Cross: SMA{fast_p}={cur_fast:.2f} crossed below SMA{slow_p}={cur_slow:.2f} on {timeframe}")
    return None


def rule_macd_bullish_crossover(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("macd_bullish_crossover", {})
    if not cfg.get("enabled", True): return None
    cur_line, cur_sig = ind.get("MACD_LINE"), ind.get("MACD_SIGNAL")
    prev_line, prev_sig = prev_ind.get("MACD_LINE"), prev_ind.get("MACD_SIGNAL")
    if not all(_valid(v) for v in [cur_line, cur_sig, prev_line, prev_sig]): return None
    if cur_line > cur_sig and prev_line <= prev_sig:
        return _make_signal(symbol, "MACD_BULLISH_XOVER", timeframe, dt, round(cur_line, 4), round(cur_sig, 4),
                            cfg.get("severity", "info"),
                            f"{symbol} MACD bullish crossover: MACD={cur_line:.3f} crossed above signal={cur_sig:.3f} on {timeframe}")
    return None


def rule_macd_bearish_crossover(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("macd_bearish_crossover", {})
    if not cfg.get("enabled", True): return None
    cur_line, cur_sig = ind.get("MACD_LINE"), ind.get("MACD_SIGNAL")
    prev_line, prev_sig = prev_ind.get("MACD_LINE"), prev_ind.get("MACD_SIGNAL")
    if not all(_valid(v) for v in [cur_line, cur_sig, prev_line, prev_sig]): return None
    if cur_line < cur_sig and prev_line >= prev_sig:
        return _make_signal(symbol, "MACD_BEARISH_XOVER", timeframe, dt, round(cur_line, 4), round(cur_sig, 4),
                            cfg.get("severity", "info"),
                            f"{symbol} MACD bearish crossover: MACD={cur_line:.3f} crossed below signal={cur_sig:.3f} on {timeframe}")
    return None


def rule_near_52w_high(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("near_52w_high", {})
    if not cfg.get("enabled", True): return None
    pct = ind.get("PCT_FROM_52W_HIGH")
    if not _valid(pct): return None
    threshold = cfg.get("proximity_pct", 5.0)
    if pct <= threshold:
        return _make_signal(symbol, "NEAR_52W_HIGH", timeframe, dt, round(pct, 2), threshold,
                            cfg.get("severity", "info"),
                            f"{symbol} is {pct:.1f}% from 52-week high (within {threshold}%) on {timeframe}")
    return None


def rule_near_52w_low(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("near_52w_low", {})
    if not cfg.get("enabled", True): return None
    pct = ind.get("PCT_FROM_52W_LOW")
    if not _valid(pct): return None
    threshold = cfg.get("proximity_pct", 5.0)
    if pct <= threshold:
        return _make_signal(symbol, "NEAR_52W_LOW", timeframe, dt, round(pct, 2), threshold,
                            cfg.get("severity", "alert"),
                            f"{symbol} is {pct:.1f}% from 52-week low (within {threshold}%) on {timeframe}")
    return None


def rule_bb_squeeze(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("bb_squeeze", {})
    if not cfg.get("enabled", True): return None
    bb_width = ind.get("BB_WIDTH")
    bb_middle = ind.get("BB_MIDDLE")
    if not _valid(bb_width) or not _valid(bb_middle) or bb_middle == 0: return None
    bandwidth = bb_width / bb_middle
    threshold = cfg.get("bandwidth_threshold", 0.05)
    if bandwidth < threshold:
        return _make_signal(symbol, "BB_SQUEEZE", timeframe, dt, round(bandwidth, 4), threshold,
                            cfg.get("severity", "info"),
                            f"{symbol} BB squeeze: bandwidth={bandwidth:.3f} below {threshold} on {timeframe}")
    return None


def rule_bb_breakout_upper(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("bb_breakout_upper", {})
    if not cfg.get("enabled", True): return None
    close = ind.get("close")
    bb_upper = ind.get("BB_UPPER")
    if not _valid(close) or not _valid(bb_upper): return None
    if close > bb_upper:
        return _make_signal(symbol, "BB_BREAKOUT_UP", timeframe, dt, round(close, 2), round(bb_upper, 2),
                            cfg.get("severity", "warning"),
                            f"{symbol} price={close:.2f} broke above BB upper={bb_upper:.2f} on {timeframe}")
    return None


def rule_bb_breakout_lower(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("bb_breakout_lower", {})
    if not cfg.get("enabled", True): return None
    close = ind.get("close")
    bb_lower = ind.get("BB_LOWER")
    if not _valid(close) or not _valid(bb_lower): return None
    if close < bb_lower:
        return _make_signal(symbol, "BB_BREAKOUT_DOWN", timeframe, dt, round(close, 2), round(bb_lower, 2),
                            cfg.get("severity", "warning"),
                            f"{symbol} price={close:.2f} broke below BB lower={bb_lower:.2f} on {timeframe}")
    return None


def rule_volume_spike(symbol, timeframe, dt, ind, prev_ind, config) -> Optional[dict]:
    cfg = config["signals"]["rules"].get("volume_spike", {})
    if not cfg.get("enabled", True): return None
    vol_ratio = ind.get("VOL_RATIO")
    if not _valid(vol_ratio): return None
    multiplier = cfg.get("multiplier", 2.0)
    if vol_ratio > multiplier:
        return _make_signal(symbol, "VOLUME_SPIKE", timeframe, dt, round(vol_ratio, 2), multiplier,
                            cfg.get("severity", "info"),
                            f"{symbol} volume spike: {vol_ratio:.1f}x average on {timeframe}")
    return None


ALL_RULES = [
    rule_rsi_oversold,
    rule_rsi_overbought,
    rule_golden_cross,
    rule_death_cross,
    rule_macd_bullish_crossover,
    rule_macd_bearish_crossover,
    rule_near_52w_high,
    rule_near_52w_low,
    rule_bb_squeeze,
    rule_bb_breakout_upper,
    rule_bb_breakout_lower,
    rule_volume_spike,
]
