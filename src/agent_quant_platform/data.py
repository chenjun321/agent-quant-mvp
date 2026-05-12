from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import sin
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import MarketBar


BINANCE_REST_URL = "https://api.binance.com"


class BinanceSpotDataClient:
    """Read-only Binance Spot market data client.

    This class intentionally does not know anything about API keys or trading.
    The first production step is paper trading, so public market data is enough.
    """

    def __init__(self, base_url: str = BINANCE_REST_URL, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_klines(self, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 240) -> list[MarketBar]:
        query = urlencode({"symbol": symbol.upper(), "interval": interval, "limit": limit})
        url = f"{self.base_url}/api/v3/klines?{query}"
        request = Request(url, headers={"User-Agent": "agent-quant-platform/0.1"})

        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        bars: list[MarketBar] = []
        for item in payload:
            bars.append(
                MarketBar(
                    ts=datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).replace(tzinfo=None),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    symbol=symbol.upper(),
                    interval=interval,
                    source="binance",
                )
            )
        return bars


def generate_mock_bars(symbol: str, periods: int = 240, interval: str = "1h") -> list[MarketBar]:
    start = datetime(2025, 1, 1, 0, 0, 0)
    price = 100.0
    bars: list[MarketBar] = []

    for idx in range(periods):
        wave = sin(idx / 11) * 1.8
        drift = 0.08 if idx < periods * 0.35 else (-0.04 if idx < periods * 0.7 else 0.12)
        shock = ((idx % 13) - 6) * 0.03

        close = max(1.0, price + wave + drift + shock)
        high = max(price, close) + 0.6
        low = min(price, close) - 0.6
        volume = 1000 + (idx % 17) * 35 + abs(wave) * 40

        bars.append(
            MarketBar(
                ts=start + timedelta(hours=idx),
                open=round(price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=round(volume, 4),
                symbol=symbol.upper(),
                interval=interval,
                source="mock",
            )
        )
        price = close

    return bars


def load_market_bars(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 240,
    source: str = "mock",
    fallback_to_mock: bool = True,
) -> list[MarketBar]:
    if source == "mock":
        return generate_mock_bars(symbol=symbol, periods=limit, interval=interval)

    if source != "binance":
        raise ValueError("source must be 'mock' or 'binance'")

    try:
        return BinanceSpotDataClient().fetch_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception:
        if not fallback_to_mock:
            raise
        return generate_mock_bars(symbol=symbol, periods=limit, interval=interval)
