# Korean Stock Price API

한국 주식 현재가를 제공하는 FastAPI 서버입니다.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/prices` | 전체 종목 현재가 반환 |
| GET | `/health` | 서버 상태 확인 |

### 응답 예시

```json
// GET /prices
{
  "005930": 54100,
  "009830": 23000,
  "101490": 38000
}
```

## 로컬 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Railway 배포

1. [railway.app](https://railway.app) 가입 후 로그인
2. **New Project → Deploy from GitHub repo** 선택
3. 이 저장소 연결 (GitHub에 push 필요)
4. Railway가 `Procfile`을 자동 감지해 배포 시작
5. 배포 완료 후 **Settings → Domains → Generate Domain** 으로 URL 발급

### GitHub에 올리기

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<your-id>/stock-api.git
git push -u origin main
```

> Railway Free 플랜은 월 500시간 제공됩니다.
