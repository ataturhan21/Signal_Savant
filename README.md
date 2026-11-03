# Signal Savant

A Python Telegram bot that retrieves OHLCV data through CCXT, calculates a volume/price ratio (VPR), and returns a candlestick chart with the indicator.

The active entry point is [`run.py`](run.py). The file `signal_savant/app.py` is empty; there is no implemented Streamlit interface.

## Local setup

The original environment uses Python 3.9 and Poetry 1.4.0. Dependency versions are recorded in [`pyproject.toml`](pyproject.toml) and `poetry.lock`.

```bash
git clone https://github.com/ataturhan21/Signal_Savant.git
cd Signal_Savant
poetry install --no-root
```

Create `.env` in the repository root using [`.env.example`](.env.example), then set:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Required Telegram bot credential used when `run.py` starts |
| `USER_ID` | Destination chat ID used by `send_signal` if scheduled delivery is explicitly enabled |

The existing `.gitignore` excludes `.env`. Keep real credentials in that ignored file.

If `BOT_TOKEN` is missing, `run.py` exits with a message naming the variable.

Start from the repository root:

```bash
poetry run python run.py
```

On Windows, [`script/start_app.bat`](script/start_app.bat) resolves the working directory automatically.

## Commands and behavior

- `/signal`: fetch market data and reply with an OHLC/VPR chart.
- `/start` and `/help`: list the available commands.
- Other messages: point to `/help`.

The scheduling example in `run.py` (`start_scheduler()`) is never called. Running the bot starts Telegram polling; it does not enable periodic signal pushes. Chart export uses Plotly and Kaleido.

## Market configuration

Edit [`config.py`](config.py) before running:

| Setting | Committed example |
| --- | --- |
| Exchange and symbol | `binance`, `BTC/USDT` |
| Source and target interval | `5m` to `1h` |
| Download start | `2023-01-01T00:00:00Z` |
| Fetch limit | `1000` |
| Upper and lower VPR thresholds | `60` and `40` |
| Chart history | `60` rows |

The configured history can cause a substantial initial download. Exchange access and Telegram credentials are required for a live run. Indicator thresholds are implementation settings, not a demonstrated prediction accuracy.

## Project map

- [`run.py`](run.py): environment loading, Telegram handlers, and the inactive `start_scheduler()` example.
- [`utils.py`](utils.py): market downloads, resampling, VPR calculation, and image generation.
- [`config.py`](config.py): the default market and indicator parameters.

The original dependency constraints are preserved. Live exchange requests, Telegram delivery, and current provider compatibility are separate from local calculation tests.

## Offline regression checks

The tests use a fake exchange and synthetic candles; they do not contact an
exchange or Telegram. Downloads retry transient network failures at most 3
times per request, retain single-candle pages, and stop with an error if
pagination cannot advance.

```bash
poetry run python -m unittest discover -s tests -v
```

Without Poetry, the tests need only NumPy and pandas (this is what CI installs):

```bash
python -m pip install "numpy>=1.26.2,<2" "pandas>=2.1.4,<3"
python -m unittest discover -s tests -v
```

## License

[MIT](LICENSE).
