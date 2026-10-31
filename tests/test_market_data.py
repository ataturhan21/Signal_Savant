"""Offline exchange pagination and VPR regression tests."""

import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

import utils


class NetworkError(Exception):
    pass


class Exchange:
    rateLimit = 1
    has = {"fetchOHLCV": True}

    def __init__(self, pages):
        self.pages = iter(pages)
        self.cursors = []
        self.sleeps = []

    def parse8601(self, value):
        return 0 if value == "valid" else None

    def load_markets(self):
        return {}

    def milliseconds(self):
        return 100

    def sleep(self, delay):
        self.sleeps.append(delay)

    def fetch_ohlcv(self, **kwargs):
        self.cursors.append(kwargs["since"])
        value = next(self.pages)
        if isinstance(value, Exception):
            raise value
        return value


def candle(timestamp):
    return [timestamp, 1, 2, 0, 1, 10]


class MarketDataTests(unittest.TestCase):
    def fetch(self, exchange, **kwargs):
        ccxt = types.SimpleNamespace(test=lambda config: exchange, NetworkError=NetworkError)
        with patch.dict(sys.modules, {"ccxt": ccxt}):
            return utils.get_data("TEST/PAIR", "test", "1m", "valid", 10, **kwargs)

    def test_keeps_single_candle_pages_and_advances(self):
        exchange = Exchange([[candle(0)], [candle(1)], []])
        result = self.fetch(exchange)
        self.assertEqual(len(result), 2)
        self.assertEqual(exchange.cursors, [0, 1, 2])

    def test_rejects_non_advancing_page(self):
        exchange = Exchange([[candle(0)], [candle(0)]])
        with self.assertRaisesRegex(RuntimeError, "non-advancing"):
            self.fetch(exchange)

    def test_transient_failure_retries_same_page(self):
        exchange = Exchange([NetworkError(), [candle(0)], []])
        self.assertEqual(len(self.fetch(exchange)), 1)
        self.assertEqual(exchange.cursors, [0, 0, 1])
        self.assertEqual(exchange.sleeps, [1])

    def test_network_retries_are_bounded(self):
        exchange = Exchange([NetworkError(), NetworkError(), NetworkError()])
        with self.assertRaises(NetworkError):
            self.fetch(exchange, max_retries=2)
        self.assertEqual(len(exchange.cursors), 3)

    def test_permanent_error_is_not_retried(self):
        exchange = Exchange([ValueError("bad symbol")])
        with self.assertRaisesRegex(ValueError, "bad symbol"):
            self.fetch(exchange)
        self.assertEqual(len(exchange.cursors), 1)

    def test_unsupported_exchange_fails_before_fetch(self):
        exchange = Exchange([])
        exchange.has = {"fetchOHLCV": False}
        with self.assertRaisesRegex(ValueError, "does not support"):
            self.fetch(exchange)
        self.assertEqual(exchange.cursors, [])

    def test_empty_history_has_stable_schema(self):
        result = self.fetch(Exchange([[]]))
        self.assertEqual(list(result.columns), ["Date", "Open", "High", "Low", "Close", "Volume", "Symbol"])
        self.assertTrue(result.empty)

    def test_vpr_is_named_and_does_not_collide_with_close(self):
        prices = [100, 101, 100, 102]
        frame = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=4, freq="15min"),
                              "Open": prices, "High": prices, "Low": prices, "Close": prices,
                              "Volume": [10] * 4, "Symbol": ["TEST"] * 4})
        config = types.SimpleNamespace(symbol="TEST", exchange_id="test", timeframe_from="15m",
            timeframe_to="1h", since="valid", limit=10, hard_to_grow_th=60, hard_to_fall_th=40)
        with patch.object(utils, "get_data", return_value=frame):
            result = utils.get_signal(config)
        self.assertEqual(list(result.columns).count("Close"), 1)
        self.assertIn("vpr", result)
        self.assertAlmostEqual(result.vpr.iloc[0], 25.001, places=3)

    def test_empty_signal_history_has_actionable_error(self):
        config = types.SimpleNamespace(symbol="TEST", exchange_id="test", timeframe_from="15m",
            timeframe_to="1h", since="valid", limit=10)
        with patch.object(utils, "get_data", return_value=pd.DataFrame()):
            with self.assertRaisesRegex(ValueError, "No OHLCV"):
                utils.get_signal(config)


if __name__ == "__main__":
    unittest.main()
