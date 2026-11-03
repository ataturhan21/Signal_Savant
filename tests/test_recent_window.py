"""Offline checks that the default download covers only the charted window."""

import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import utils
from config import create_config

NOW = pd.Timestamp("2024-01-05 10:17:00")


def make_config(**overrides):
    values = dict(symbol="TEST", exchange_id="test", timeframe_from="5m", timeframe_to="1h",
                  since=None, limit=1000, hard_to_grow_th=60, hard_to_fall_th=40, data_horizon=24)
    values.update(overrides)
    return types.SimpleNamespace(**values)


def candles(start, end):
    dates = pd.date_range(start, end, freq="5min")
    rng = np.random.default_rng(7)
    close = 100 + rng.normal(0, 1, len(dates)).cumsum().round(2)
    return pd.DataFrame({"Date": dates, "Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": rng.integers(1, 100, len(dates)),
                         "Symbol": "TEST"})


class RecentWindowTests(unittest.TestCase):
    def test_window_starts_one_candle_before_the_first_charted_bucket(self):
        first_bucket, since = utils.recent_window(make_config(), NOW)
        self.assertEqual(first_bucket, pd.Timestamp("2024-01-04 10:00:00"))
        self.assertEqual(since, "2024-01-04T09:55:00Z")

    def test_aware_now_is_read_as_utc(self):
        _, since = utils.recent_window(make_config(), pd.Timestamp("2024-01-05 05:17", tz="US/Eastern"))
        self.assertEqual(since, "2024-01-04T09:55:00Z")

    def test_recent_window_matches_full_history(self):
        history = candles("2024-01-01", NOW.floor("5min"))

        def download(**kwargs):
            start = pd.Timestamp(kwargs["since"]).tz_convert(None)
            return history[history.Date >= start].reset_index(drop=True)

        with patch.object(utils, "get_data", return_value=history):
            full = utils.get_signal(make_config(since="2024-01-01T00:00:00Z"))
        with patch.object(utils, "get_data", side_effect=download) as fetch:
            recent = utils.get_signal(make_config(), now=NOW)

        self.assertEqual(fetch.call_args.kwargs["since"], "2024-01-04T09:55:00Z")
        self.assertEqual(len(recent), 25)  # 24 full buckets plus the current one
        expected = full[full.Date >= recent.Date.iloc[0]].reset_index(drop=True)
        pd.testing.assert_frame_equal(recent, expected)

    def test_explicit_since_downloads_from_that_time(self):
        history = candles("2024-01-05", NOW.floor("5min"))
        with patch.object(utils, "get_data", return_value=history) as fetch:
            utils.get_signal(make_config(since="2023-01-01T00:00:00Z"), now=NOW)
        self.assertEqual(fetch.call_args.kwargs["since"], "2023-01-01T00:00:00Z")

    def test_default_config_fits_in_one_page(self):
        config = create_config()
        self.assertIsNone(config.since)
        first_bucket, since = utils.recent_window(config, NOW)
        span = NOW - pd.Timestamp(since).tz_convert(None)
        self.assertLessEqual(span / pd.to_timedelta(config.timeframe_from) + 1, config.limit)
        self.assertEqual(first_bucket, NOW.floor("1h") - config.data_horizon * pd.Timedelta("1h"))

    def test_calendar_intervals_are_rejected_with_a_clear_message(self):
        with self.assertRaisesRegex(ValueError, "fixed intervals"):
            utils.recent_window(make_config(timeframe_to="1M"), NOW)


if __name__ == "__main__":
    unittest.main()
