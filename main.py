import os
import time
import threading
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

APP_KEY    = os.environ.get("KIS_APP_KEY", "")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "")

BASE_URL = "https://openapi.koreainvestment.com:9443"

TICKERS = ["005930", "009830", "101490"]
PRICE_CACHE_TTL = 30  # seconds

app = FastAPI(title="Korean Stock Price API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 토큰 캐시 ──────────────────────────────────────────
_token: str = ""
_token_expires_at: float = 0
_token_lock = threading.Lock()

def get_token() -> str:
    global _token, _token_expires_at
    with _token_lock:
        if time.time() < _token_expires_at - 60:   # 만료 1분 전까지 재사용
            return _token
        resp = requests.post(
            f"{BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": APP_KEY,
                "appsecret": APP_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        # expires_in(초) 필드가 있으면 사용, 없으면 6시간 기본값
        expires_in = int(data.get("expires_in", 21600))
        _token_expires_at = time.time() + expires_in
        return _token


# ── 주가 캐시 ──────────────────────────────────────────
_price_cache: dict = {}
_price_cache_time: float = 0
_price_lock = threading.Lock()

def fetch_price(ticker: str, token: str) -> int | None:
    resp = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers={
            "Authorization": f"Bearer {token}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": "FHKST01010100",
            "Content-Type": "application/json",
        },
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    price_str = data.get("output", {}).get("stck_prpr")
    return int(price_str) if price_str else None

def fetch_all_prices() -> dict:
    token = get_token()
    result = {}
    for ticker in TICKERS:
        try:
            result[ticker] = fetch_price(ticker, token)
        except Exception as e:
            print(f"[WARN] {ticker}: {e}")
            result[ticker] = None
    return result

def get_prices() -> dict:
    global _price_cache, _price_cache_time
    now = time.time()
    with _price_lock:
        if now - _price_cache_time >= PRICE_CACHE_TTL or not _price_cache:
            _price_cache = fetch_all_prices()
            _price_cache_time = now
        return dict(_price_cache)


# ── 엔드포인트 ─────────────────────────────────────────
@app.get("/prices")
def prices():
    if not APP_KEY or not APP_SECRET:
        raise HTTPException(status_code=500, detail="KIS_APP_KEY / KIS_APP_SECRET not set")
    return get_prices()

@app.get("/health")
def health():
    return {"status": "ok"}
