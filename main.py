import time
import threading
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Korean Stock Price API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# yfinance 종목코드 → 응답 키 매핑
TICKERS = {
    "005930.KS": "005930",
    "009830.KS": "009830",
    "101490.KS": "101490",
}

CACHE_TTL = 30  # seconds

_cache: dict = {}
_cache_time: float = 0
_lock = threading.Lock()


def fetch_prices() -> dict:
    result = {}
    for yf_ticker, code in TICKERS.items():
        try:
            ticker = yf.Ticker(yf_ticker)
            info = ticker.fast_info
            price = info.last_price
            result[code] = int(price) if price else None
        except Exception as e:
            print(f"[WARN] {yf_ticker}: {e}")
            result[code] = None
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
