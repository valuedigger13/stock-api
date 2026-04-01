import os
import time
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import FinanceDataReader as fdr

app = FastAPI(title="Korean Stock Price API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TICKERS = ["005930", "009830", "101490"]
CACHE_TTL = 30  # seconds

_cache: dict = {}
_cache_time: float = 0
_lock = threading.Lock()


def fetch_prices() -> dict:
    result = {}
    for ticker in TICKERS:
        try:
            df = fdr.DataReader(ticker, exchange="KRX")
            if not df.empty:
                result[ticker] = int(df["Close"].iloc[-1])
            else:
                result[ticker] = None
        except Exception as e:
            print(f"[WARN] {ticker}: {e}")
            result[ticker] = None
    return result


def get_prices() -> dict:
    global _cache, _cache_time
    now = time.time()
    with _lock:
        if now - _cache_time >= CACHE_TTL or not _cache:
            _cache = fetch_prices()
            _cache_time = now
        return dict(_cache)


@app.get("/prices")
def prices():
    return get_prices()


@app.get("/health")
def health():
    return {"status": "ok"}
