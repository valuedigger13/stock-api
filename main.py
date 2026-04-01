import time
import threading
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pykrx import stock

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


def latest_trading_date() -> str:
    """오늘 또는 가장 최근 거래일을 YYYYMMDD 형태로 반환"""
    today = datetime.today()
    for i in range(7):
        d = today - timedelta(days=i)
        # 주말 제외 (0=월 ~ 4=금)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return today.strftime("%Y%m%d")


def fetch_prices() -> dict:
    result = {}
    date = latest_trading_date()
    for ticker in TICKERS:
        try:
            df = stock.get_market_ohlcv_by_date(date, date, ticker)
            if not df.empty:
                result[ticker] = int(df["종가"].iloc[-1])
            else:
                # 당일 데이터 없으면 최근 5일치로 재시도
                from_date = (datetime.strptime(date, "%Y%m%d") - timedelta(days=10)).strftime("%Y%m%d")
                df2 = stock.get_market_ohlcv_by_date(from_date, date, ticker)
                result[ticker] = int(df2["종가"].iloc[-1]) if not df2.empty else None
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
