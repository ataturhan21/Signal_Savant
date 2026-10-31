from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import addict

import pandas as pd
import numpy as np


def get_data(
    symbol: str, exchange_id: str, timeframe: str, since: str, limit: int,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Download OHLCV history, retrying only transient network failures.

    Each failed request gets at most max_retries retries. Pagination advances
    past the last candle and rejects a non-advancing exchange response.
    """
    import ccxt

    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"timeout": 30000, "enableRateLimit": True})
    since_ms = exchange.parse8601(since)
    if since_ms is None:
        raise ValueError("since must be an ISO 8601 timestamp")

    def request(operation):
        for attempt in range(max_retries + 1):
            try:
                return operation()
            except ccxt.NetworkError:
                if attempt == max_retries:
                    raise
                exchange.sleep(exchange.rateLimit * (attempt + 1))

    request(exchange.load_markets)
    if not exchange.has.get("fetchOHLCV"):
        raise ValueError(f"{exchange_id} does not support OHLCV downloads")
    end_ms = exchange.milliseconds()
    all_orders = []
    while since_ms < end_ms:
        orders = request(lambda: exchange.fetch_ohlcv(
            symbol=symbol, timeframe=timeframe, since=since_ms, limit=limit
        ))
        if not orders:
            break
        last_timestamp = max(order[0] for order in orders)
        if last_timestamp < since_ms:
            raise RuntimeError("Exchange returned a non-advancing OHLCV page")
        all_orders.extend(order for order in orders if since_ms <= order[0] <= end_ms)
        since_ms = last_timestamp + 1

    data = pd.DataFrame(
        all_orders, columns=["Date", "Open", "High", "Low", "Close", "Volume"]
    )
    data = data.drop_duplicates(subset="Date", keep="last").sort_values("Date").reset_index(drop=True)
    data["Date"] = pd.to_datetime(data["Date"], unit="ms")
    data["Symbol"] = symbol
    return data


def get_signal(config: addict.Dict) -> pd.DataFrame:
    # Download data
    data = get_data(
        symbol=config.symbol,
        exchange_id=config.exchange_id,
        timeframe=config.timeframe_from,
        since=config.since,
        limit=config.limit,
    )

    if data.empty:
        raise ValueError("No OHLCV data was returned for this market and date range")

    # Prepare data to compute vpr
    data = data.set_index("Date")
    data["return"] = data.Close.diff()
    data["positive_return"] = (data["return"] > 0).astype(int)

    data["volume_price_pos"] = 0
    data["volume_price_neg"] = 0

    def calculate_vpr(ser: pd.Series) -> float:
        # Select portion of data
        window = data.loc[ser.index]

        # Computes sums of negative and positive returns
        positive_return = window[window["positive_return"] == 1]
        negative_return = window[window["positive_return"] == 0]
        return_pos_sum = positive_return["return"].sum()
        return_neg_sum = negative_return["return"].sum()

        # Check for zero division
        if return_pos_sum == 0 or return_neg_sum == 0:
            return np.nan

        # Computes Volumes in positive and negative returns
        volume_price_pos = (positive_return["Volume"].sum() / return_pos_sum).round(3)
        volume_price_neg = (negative_return["Volume"].sum() / return_neg_sum).round(3)

        if (abs(volume_price_pos) + abs(volume_price_neg)) == 0:
            return np.nan

        # Calculate vpr
        vpr = (
            abs(volume_price_pos)
            * 100
            / (abs(volume_price_pos) + abs(volume_price_neg))
        ).round(3)

        return vpr

    # Resample to the target timeframe and apply calculate_vpr
    # as aggregation function to get vpr
    vpr = data["Close"].resample(config.timeframe_to).apply(calculate_vpr).rename("vpr")

    # Resample all data to the target timeframe
    resampled_data = data.resample(config.timeframe_to).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
            "Symbol": "first",
        }
    )

    # Add vpr to the main dataframe
    resampled_data = resampled_data.join(vpr).reset_index()

    # Calculate signals
    resampled_data["hard_to_grow"] = resampled_data.vpr >= config.hard_to_grow_th
    resampled_data["hard_to_fall"] = resampled_data.vpr <= config.hard_to_fall_th

    return resampled_data


def create_plot(config: addict.Dict, data: pd.DataFrame) -> bytes:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    data = data.tail(config.data_horizon)
    fig = make_subplots(
        rows=2,
        cols=1,
        start_cell="top-left",
        subplot_titles=("OHLC", "VPR"),
        vertical_spacing=0.05,
    )
    fig.add_trace(
        go.Candlestick(
            x=data["Date"],
            open=data["Open"],
            high=data["High"],
            low=data["Low"],
            close=data["Close"],
            increasing_line_color="green",
            decreasing_line_color="red",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data["Date"], y=data["vpr"], line_color="red", mode="lines", name="vpr"
        ),
        row=2,
        col=1,
    )
    fig = fig.update_layout(
        hovermode="x",
        height=900,
        width=1000,
        title_text="VPR",
        xaxis_rangeslider_visible=False,
    )
    fig = fig.to_image(format="png")

    return fig

