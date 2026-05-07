# NASDAQ Top 30 Daily Report

매일 미국 장 마감 후 **나스닥 거래대금(Dollar Volume) 상위 30개 종목**을 자동 분석하여 이메일로 발송하는 시스템입니다.

## 주요 기능

### 거래대금 Top 30 분석
- 종가 × 거래량 기준 **Dollar Volume 상위 30개 종목** 선별
- 전일 대비 **등락률** 표시
- **신고가 돌파** / **신고가 접근중** (ATH 90% 이상) 태그

### 섹터별 거래대금 트리맵
- Industry 기반 **세분화 섹터 분류** (한국어, ~50개 산업군)
- 섹터별 거래대금 비중을 **트리맵 차트**로 시각화
- 각 블록에 섹터명 + 거래대금 1위 대표 종목 표시

### 섹터별 관련 뉴스
- Yahoo Finance RSS + Bing News RSS 이중 소스
- **관련성 스코어링**: 최신순(30점) + 티커 매칭(25점) + 섹터 키워드(15점) + 출처 신뢰도(10점)
- 제목 유사도 70% 기준 **중복 제거**
- Google Translate API로 **한국어 번역**

### 글로벌 시장 지표 (8개, 3개월 차트)
| 지표 | 설명 |
|------|------|
| VIX 공포지수 | 시장 변동성 기대치 |
| 달러인덱스 DXY | 달러 강세/약세 |
| 미 10년물 금리 | 장기 금리, 성장주 밸류에이션 영향 |
| WTI 유가 | 에너지 비용, 인플레 압력 |
| S&P 500 | 미국 대형주 방향성 |
| NASDAQ | 기술주 중심 방향성 |
| 금 Gold | 안전자산 수요 |
| 원달러 환율 | 원화 가치, 외국인 투자 매력 |

- 각 지표별 **3개월 라인 차트** (2×4 그리드) 시각화
- 현재 수준 해석 + 3개월 트렌드 + 단기 모멘텀 코멘트

## 리포트 구성

```
1. 헤더 (날짜, 총 거래대금, 신고가 종목 수, 섹터 수)
2. 섹터별 거래대금 분포 트리맵 (PNG 차트)
3. 거래대금 순위 TOP 30 테이블
4. 섹터별 상세 분석 (종목 테이블 + 관련 뉴스 3건)
5. 글로벌 시장 지표 차트 (2×4 그리드 PNG)
6. 지표별 해석 테이블
```

## 기술 스택

- **Python 3.12**
- **yfinance** — 시장 데이터 / 종목 정보 / 지표 시계열
- **matplotlib** — 트리맵 / 지표 차트 PNG 생성
- **requests** — NASDAQ API / RSS 뉴스 수집
- **Gmail SMTP** — CID 이미지 첨부 이메일 발송
- **GitHub Actions** — 자동 스케줄 실행

## 자동 실행 (GitHub Actions)

매주 **월~금 한국시간 06:00** (UTC 21:00)에 자동 실행됩니다.

### 필요한 GitHub Secrets

| Secret | 설명 |
|--------|------|
| `GMAIL_USER` | 발신 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (16자리) |
| `RECIPIENT_EMAIL` | 수신자 이메일 (콤마로 복수 지정 가능) |

### 수동 실행

GitHub → Actions → **NASDAQ Daily Report** → **Run workflow**

## 로컬 실행

```bash
pip install -r requirements.txt
python nasdaq_top30.py
```

환경변수 설정 시 자동 발송 모드로 동작:
```bash
GMAIL_USER="your@gmail.com" \
GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
RECIPIENT_EMAIL="recipient1@gmail.com,recipient2@gmail.com" \
python nasdaq_top30.py
```

## 프로젝트 구조

```
nasdaq-top30/
├── nasdaq_top30.py              # 메인 스크립트
├── requirements.txt             # Python 의존성
├── .github/
│   └── workflows/
│       └── nasdaq_report.yml    # GitHub Actions 워크플로우
├── .gitignore
└── README.md
```

## 출력 파일 (런타임 생성)

| 파일 | 설명 |
|------|------|
| `nasdaq_report_YYYYMMDD.html` | HTML 리포트 (로컬 브라우저 확인용) |
| `nasdaq_top30_YYYYMMDD.csv` | Top 30 종목 데이터 CSV |
