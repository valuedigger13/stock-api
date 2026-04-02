import os
import time
import threading
import requests
from datetime import date
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import anthropic

load_dotenv()

APP_KEY       = os.environ.get("KIS_APP_KEY", "")
APP_SECRET    = os.environ.get("KIS_APP_SECRET", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BASE_URL = "https://openapi.koreainvestment.com:9443"
TICKERS  = ["005930", "489790", "101490"]
PRICE_CACHE_TTL = 30  # seconds

app = FastAPI(title="Korean Stock Price API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 사주 정보 ──────────────────────────────────────────
SAJU = {
    "도원": {
        "name": "서도원(남편)",
        "birth": "1988년 3월 17일 인시생(寅時, 03:00~05:00)",
        "ilgan": "辛金 일간",
        "pillars": "庚寅·辛未·乙卯·戊辰",
    },
    "은아": {
        "name": "남은아(부인)",
        "birth": "1989년 7월 15일 오후 3시 32분생",
        "ilgan": "丙火 일간",
        "pillars": "丙申·丙子·辛未·己巳",
    },
    "규빈": {
        "name": "서규빈(첫째)",
        "birth": "2021년 5월 23일 오후 11시생",
        "ilgan": "己土 일간",
        "pillars": "戊子·己未·辛巳·辛丑",
    },
    "이재": {
        "name": "서이재(둘째)",
        "birth": "2026년 1월 5일 오후 8시 49분생",
        "ilgan": "己土 일간",
        "pillars": "乙巳·己丑·己卯·甲戌",
    },
    "가족": {
        "name": "서도원 가족 전체",
        "birth": "",
        "ilgan": "",
        "pillars": "서도원(辛金)·남은아(丙火)·서규빈(己土)·서이재(己土)",
    },
}

NEWS_TOPICS = {
    "all":    "삼성전자, 한화비전, 에스앤에스텍 관련 최신 주식/비즈니스 뉴스",
    "samsung":"삼성전자(005930) 관련 최신 주식/비즈니스 뉴스",
    "hanwha": "한화비전(489790) 관련 최신 주식/비즈니스 뉴스",
    "sns":    "에스앤에스텍(101490) 관련 최신 주식/비즈니스 뉴스",
}

# ── KIS 토큰 캐시 ───────────────────────────────────────
_token: str = ""
_token_expires_at: float = 0
_token_lock = threading.Lock()

def get_token() -> str:
    global _token, _token_expires_at
    with _token_lock:
        if time.time() < _token_expires_at - 60:
            return _token
        resp = requests.post(
            f"{BASE_URL}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        _token_expires_at = time.time() + int(data.get("expires_in", 21600))
        return _token

# ── 주가 캐시 ───────────────────────────────────────────
_price_cache: dict = {}
_price_cache_time: float = 0
_price_lock = threading.Lock()

def fetch_price(ticker: str, token: str):
    resp = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers={
            "Authorization": f"Bearer {token}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": "FHKST01010100",
            "Content-Type": "application/json",
        },
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        timeout=10,
    )
    resp.raise_for_status()
    price_str = resp.json().get("output", {}).get("stck_prpr")
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

# ── Claude 호출 헬퍼 ────────────────────────────────────
def claude_client() -> anthropic.Anthropic:
    if not ANTHROPIC_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ── 엔드포인트 ──────────────────────────────────────────
@app.get("/prices")
def prices():
    if not APP_KEY or not APP_SECRET:
        raise HTTPException(status_code=500, detail="KIS_APP_KEY / KIS_APP_SECRET not set")
    return get_prices()


@app.get("/news")
def news(topic: str = Query(default="all")):
    if topic not in NEWS_TOPICS:
        raise HTTPException(status_code=400, detail=f"topic must be one of: {list(NEWS_TOPICS.keys())}")

    query_text = NEWS_TOPICS[topic]
    today = date.today().strftime("%Y년 %m월 %d일")

    client = claude_client()
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": (
                f"오늘은 {today}입니다. "
                f"{query_text}를 웹에서 검색하고, "
                "가장 중요한 뉴스 4~5개를 아래 JSON 형식으로만 답해줘. "
                "다른 텍스트 없이 JSON만 출력:\n"
                '{"news": [{"title": "헤드라인", "summary": "한줄요약"}, ...]}'
            ),
        }],
    )

    # 텍스트 블록에서 JSON 파싱
    import json, re
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # 마크다운 코드블록 제거
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            try:
                return json.loads(text)
            except Exception:
                return {"news": [], "raw": text}
    return {"news": []}


@app.get("/fortune")
def fortune(member: str = Query(default="도원")):
    if member not in SAJU:
        raise HTTPException(status_code=400, detail=f"member must be one of: {list(SAJU.keys())}")

    info = SAJU[member]
    today = date.today().strftime("%Y년 %m월 %d일")

    if member == "가족":
        saju_desc = f"가족 구성원: {info['pillars']}"
    else:
        saju_desc = (
            f"이름: {info['name']}, 생년월일: {info['birth']}, "
            f"일간: {info['ilgan']}, 사주 팔자: {info['pillars']}"
        )

    client = claude_client()
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"오늘은 {today}입니다.\n"
                f"아래 사주 정보를 바탕으로 오늘의 운세를 봐줘.\n"
                f"{saju_desc}\n\n"
                "운세는 ① 투자/재물운 ② 건강운 ③ 관계운 세 항목으로 나눠서, "
                "각 2~3문장으로 친근하고 따뜻하게 한국어로 작성해줘."
            ),
        }],
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            break
    return {"fortune": text}


@app.get("/history")
def history(ticker: str = Query(...), period: str = Query("1y")):
    """
    period: 1d | 1w | 3m | 6m | 1y
    한투 API 일별 주가 조회 (국내주식 기간별 시세)
    """
    from datetime import datetime, timedelta
    token = get_token()

    today = datetime.today()
    period_map = {
        "1d": timedelta(days=2),
        "1w": timedelta(weeks=1),
        "3m": timedelta(days=92),
        "6m": timedelta(days=183),
        "1y": timedelta(days=365),
    }
    delta = period_map.get(period, timedelta(days=365))
    start_str = (today - delta).strftime("%Y%m%d")
    end_str   = today.strftime("%Y%m%d")

    resp = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": "FHKST03010100",
        },
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_str,
            "FID_INPUT_DATE_2": end_str,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        },
        timeout=10,
    )
    resp.raise_for_status()

    output = resp.json().get("output2", [])
    result = [
        {"date": r["stck_bsop_date"], "close": int(r["stck_clpr"])}
        for r in output
        if r.get("stck_clpr") and r["stck_clpr"] != "0"
    ]
    result.sort(key=lambda x: x["date"])
    return {"ticker": ticker, "data": result}


@app.get("/health")
def health():
    return {"status": "ok"}
