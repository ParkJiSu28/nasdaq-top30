#!/usr/bin/env python3
"""
NASDAQ 거래대금(Dollar Volume) Top 30 분석기 v3

기능:
- 나스닥 거래대금 상위 30개 종목 조회
- 산업(Industry) 기반 세분화 섹터 분류 (한국어)
- 신고가 돌파 / 신고가 접근(10% 이내) 태그
- 등락률 (전일 대비 변동률) 표시
- 전 섹터별 관련 뉴스 3건 (한국어 번역 + 관련성 스코어링)
- 글로벌 시장 지표 8개 + 3개월 코멘트
- HTML 이메일 발송
"""

import yfinance as yf
import pandas as pd
import requests
import time
import smtplib
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from urllib.parse import quote, parse_qs, urlparse, unquote
from difflib import SequenceMatcher
import math
import warnings
import sys
import io
import re
import os

warnings.filterwarnings("ignore")

# Windows 콘솔 UTF-8 출력 설정
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════
#  산업(Industry) → 한국어 세분화 섹터 매핑
# ═══════════════════════════════════════════════════════════════

INDUSTRY_KR = {
    # ── 반도체 ──
    "Semiconductors": "반도체",
    "Semiconductor Equipment & Materials": "반도체 장비",
    "Semiconductor Memory": "반도체(메모리)",
    # ── 하드웨어 / 스토리지 ──
    "Computer Hardware": "컴퓨터 하드웨어",
    "Consumer Electronics": "가전/전자기기",
    "Electronic Components": "전자부품",
    "Scientific & Technical Instruments": "과학/기술 장비",
    "Data Storage": "데이터 스토리지",
    "Communication Equipment": "통신장비",
    # ── 소프트웨어 ──
    "Software - Application": "소프트웨어(애플리케이션)",
    "Software - Infrastructure": "소프트웨어(인프라)",
    "Information Technology Services": "IT 서비스",
    # ── 인터넷 / 플랫폼 ──
    "Internet Content & Information": "인터넷 플랫폼",
    "Internet Retail": "이커머스(온라인 유통)",
    "Electronic Gaming & Multimedia": "게임/멀티미디어",
    # ── 미디어 / 통신 ──
    "Entertainment": "엔터테인먼트",
    "Broadcasting": "방송",
    "Telecom Services": "통신 서비스",
    "Advertising Agencies": "광고",
    # ── 금융 ──
    "Capital Markets": "자본시장/증권",
    "Financial Data & Stock Exchanges": "금융데이터/거래소",
    "Credit Services": "신용/결제 서비스",
    "Insurance - Diversified": "보험",
    "Banks - Regional": "지역은행",
    "Asset Management": "자산운용",
    # ── 바이오/헬스케어 ──
    "Biotechnology": "바이오테크",
    "Drug Manufacturers - General": "제약(대형)",
    "Drug Manufacturers - Specialty & Generic": "제약(특수/제네릭)",
    "Medical Devices": "의료기기",
    "Diagnostics & Research": "진단/연구",
    "Health Information Services": "헬스케어 IT",
    "Medical Instruments & Supplies": "의료장비/소모품",
    # ── 소비재 ──
    "Auto Manufacturers": "자동차 제조",
    "Restaurants": "외식/레스토랑",
    "Discount Stores": "할인매장/대형유통",
    "Specialty Retail": "전문 유통",
    "Apparel Retail": "의류 유통",
    "Leisure": "레저",
    "Travel Services": "여행 서비스",
    "Resorts & Casinos": "리조트/카지노",
    "Packaged Foods": "가공식품",
    "Beverages - Non-Alcoholic": "음료",
    "Household & Personal Products": "생활용품",
    "Grocery Stores": "식료품점",
    # ── 에너지 ──
    "Oil & Gas E&P": "석유/가스 탐사",
    "Oil & Gas Integrated": "석유/가스 종합",
    "Solar": "태양광",
    "Uranium": "우라늄",
    # ── 산업재 ──
    "Aerospace & Defense": "항공우주/방산",
    "Trucking": "운송/물류",
    "Specialty Industrial Machinery": "특수 산업기계",
    "Electrical Equipment & Parts": "전기장비",
    "Staffing & Employment Services": "인력/고용 서비스",
    # ── 유틸리티 ──
    "Utilities - Regulated Electric": "전력(규제)",
    "Utilities - Diversified": "유틸리티(복합)",
    "Utilities - Independent Power Producers": "독립발전",
    # ── 부동산 ──
    "REIT - Specialty": "리츠(특수)",
    "REIT - Industrial": "리츠(산업)",
    # ── 기타 ──
    "Shell Companies": "스팩/쉘컴퍼니",
}

# 대분류 섹터 → 한국어
SECTOR_KR = {
    "Technology": "기술",
    "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Financial Services": "금융",
    "Healthcare": "헬스케어",
    "Energy": "에너지",
    "Industrials": "산업재",
    "Basic Materials": "소재",
    "Real Estate": "부동산",
    "Utilities": "유틸리티",
    "N/A": "미분류",
}


def industry_to_kr(industry_en):
    """영문 Industry → 한국어 세분화 섹터"""
    if industry_en in INDUSTRY_KR:
        return INDUSTRY_KR[industry_en]
    return industry_en if industry_en and industry_en != "N/A" else "미분류"


def sector_to_kr(sector_en):
    return SECTOR_KR.get(sector_en, sector_en)


# ═══════════════════════════════════════════════════════════════
#  뉴스 헤드라인 한국어 번역
# ═══════════════════════════════════════════════════════════════

def translate_to_korean(text):
    """Google Translate 비공식 API로 영→한 번역"""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "en",
            "tl": "ko",
            "dt": "t",
            "q": text,
        }
        resp = requests.get(url, params=params, timeout=5)
        result = resp.json()
        translated = "".join(seg[0] for seg in result[0] if seg[0])
        return translated
    except Exception:
        return text  # 실패 시 원문 반환


# ═══════════════════════════════════════════════════════════════
#  1. 나스닥 종목 티커 수집
# ═══════════════════════════════════════════════════════════════

def fetch_nasdaq_tickers_from_api(limit=200):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
    try:
        url = "https://api.nasdaq.com/api/screener/stocks"
        params = {"tableType": "most_active", "exchange": "nasdaq", "limit": limit}
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("table", {}).get("rows", [])
        tickers = [row["symbol"].strip() for row in rows if row.get("symbol")]
        if tickers:
            print(f"  [OK] NASDAQ API에서 {len(tickers)}개 종목 로드")
            return tickers
    except Exception as e:
        print(f"  [FAIL] NASDAQ API 실패: {e}")
    return []


def get_fallback_nasdaq_tickers():
    return [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
        "AVGO", "COST", "NFLX", "AMD", "ADBE", "PEP", "CSCO", "INTC",
        "TMUS", "CMCSA", "TXN", "QCOM", "AMGN", "INTU", "AMAT", "ISRG",
        "BKNG", "LRCX", "ADI", "VRTX", "REGN", "MDLZ", "KLAC", "MU",
        "PANW", "SNPS", "CDNS", "MRVL", "FTNT", "PYPL", "MNST", "KDP",
        "NXPI", "MELI", "ORLY", "CTAS", "ABNB", "LULU", "CEG", "DASH",
        "WDAY", "KHC", "DXCM", "EXC", "AEP", "ODFL", "PCAR", "ROST",
        "IDXX", "GEHC", "CTSH", "FAST", "VRSK", "CPRT", "BKR", "FANG",
        "ON", "DDOG", "CDW", "GFS", "TEAM", "ZS", "BIIB",
        "CRWD", "TTD", "COIN", "ARM", "PLTR", "MDB", "APP",
        "SMCI", "MSTR", "SOFI", "LCID", "RIVN", "MARA", "RIOT",
        "MRNA", "ROKU", "SNAP", "PINS", "ZM", "DOCU", "OKTA",
        "SHOP", "UBER", "LYFT", "RBLX", "HOOD", "IONQ", "RGTI",
        "QUBT", "SOUN", "UPST", "AFRM", "HIMS", "DUOL", "GRAB",
        "NU", "SE", "PDD", "JD", "BIDU", "NTES", "LI", "NIO", "XPEV",
        "BILI", "NET", "SNOW", "PATH", "AI",
        "ASTS", "LUNR", "RKLB", "ACHR", "JOBY",
        "GILD", "ADP", "SBUX", "CHTR", "MAR", "ILMN",
        "ENPH", "FSLR", "WBD", "NCLH", "EXPE", "TTWO", "EA",
        "DKNG", "CPNG", "MNDY", "CRSP",
    ]


def collect_nasdaq_tickers():
    print("\n[1/8] 나스닥 종목 리스트 수집 중...")
    tickers = fetch_nasdaq_tickers_from_api(200)
    fallback = get_fallback_nasdaq_tickers()
    seen = set(tickers)
    for t in fallback:
        if t not in seen:
            tickers.append(t)
            seen.add(t)
    print(f"  총 {len(tickers)}개 종목 대상으로 조회 시작")
    return tickers


# ═══════════════════════════════════════════════════════════════
#  2. 시장 데이터 다운로드 & 거래대금 계산 + 등락률
# ═══════════════════════════════════════════════════════════════

def download_market_data(tickers):
    print("\n[2/8] 시장 데이터 다운로드 중 (잠시 기다려주세요)...")
    data = yf.download(tickers, period="5d", group_by="ticker", threads=True)

    results = []
    for ticker in tickers:
        try:
            ticker_data = data if len(tickers) == 1 else data[ticker]
            valid = ticker_data.dropna(subset=["Close", "Volume"])
            if len(valid) < 1:
                continue
            latest = valid.iloc[-1]
            close_price = float(latest["Close"])
            volume = int(latest["Volume"])
            dollar_volume = close_price * volume

            # 등락률 계산: 전일 종가 대비
            prev_close = None
            change_pct = 0.0
            if len(valid) >= 2:
                prev_close = float(valid.iloc[-2]["Close"])
                if prev_close > 0:
                    change_pct = ((close_price - prev_close) / prev_close) * 100

            if volume > 0 and close_price > 0:
                results.append({
                    "ticker": ticker, "close": close_price,
                    "volume": volume, "dollar_volume": dollar_volume,
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                })
        except Exception:
            continue

    df = pd.DataFrame(results)
    df = df.sort_values("dollar_volume", ascending=False).head(30).reset_index(drop=True)
    print(f"  [OK] 거래대금 기준 Top 30 선별 완료")
    return df


# ═══════════════════════════════════════════════════════════════
#  3. 종목 상세 정보 (세분화 섹터 + 신고가)
# ═══════════════════════════════════════════════════════════════

def enrich_stock_info(df):
    print("\n[3/8] 종목 상세 정보 조회 중...")

    sectors, industries, names, ath_tags, ath_prices = [], [], [], [], []

    for i, row in df.iterrows():
        ticker = row["ticker"]
        current_price = row["close"]
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            sector = info.get("sector", "N/A")
            industry = info.get("industry", "N/A")
            name = info.get("shortName", info.get("longName", ticker))

            sectors.append(sector)
            industries.append(industry)
            names.append(name)

            # 신고가 판정
            fifty_two_wk_high = info.get("fiftyTwoWeekHigh", 0)
            if fifty_two_wk_high > 0 and current_price >= fifty_two_wk_high * 0.85:
                hist = stock.history(period="max")
                all_time_high = float(hist["High"].max()) if not hist.empty else fifty_two_wk_high
            else:
                all_time_high = fifty_two_wk_high

            ath_prices.append(all_time_high)

            if all_time_high > 0 and current_price >= all_time_high * 0.99:
                ath_tags.append("[신고가 돌파]")
            elif all_time_high > 0 and current_price >= all_time_high * 0.90:
                ath_tags.append("[신고가 접근중]")
            else:
                ath_tags.append("")

            print(f"  [{i+1:2d}/30] {ticker:<6s} {industry_to_kr(industry)}")

        except Exception:
            sectors.append("N/A")
            industries.append("N/A")
            names.append(ticker)
            ath_tags.append("")
            ath_prices.append(0)
            print(f"  [{i+1:2d}/30] {ticker:<6s} 정보 조회 실패")

        time.sleep(0.15)

    df["name"] = names
    df["sector"] = sectors
    df["industry"] = industries
    df["industry_kr"] = [industry_to_kr(ind) for ind in industries]
    df["sector_kr"] = [sector_to_kr(s) for s in sectors]
    df["ath_tag"] = ath_tags
    df["all_time_high"] = ath_prices

    return df


# ═══════════════════════════════════════════════════════════════
#  4. 세분화 섹터(Industry) 기준 분석
# ═══════════════════════════════════════════════════════════════

def analyze_sectors(df):
    print("\n[4/8] 세분화 섹터별 자금 유입 분석 중...")

    sector_agg = df.groupby("industry").agg(
        total_dollar_volume=("dollar_volume", "sum"),
        stock_count=("ticker", "count"),
        tickers=("ticker", list),
        names=("name", list),
        sector=("sector", "first"),  # 대분류
    ).sort_values("total_dollar_volume", ascending=False)

    sector_agg["industry_kr"] = [industry_to_kr(ind) for ind in sector_agg.index]
    sector_agg["sector_kr"] = [sector_to_kr(s) for s in sector_agg["sector"]]

    return sector_agg


# ═══════════════════════════════════════════════════════════════
#  5. 글로벌 시장 지표 8개 조회 + 3개월 코멘트
# ═══════════════════════════════════════════════════════════════

INDICATORS = {
    "^VIX": {
        "name_kr": "VIX 공포지수",
        "unit": "",
        "desc": "시장 변동성 기대치. 낮을수록 안도, 높을수록 공포.",
    },
    "DX-Y.NYB": {
        "name_kr": "달러인덱스 DXY",
        "unit": "",
        "desc": "달러 강세/약세. 강달러 시 수출기업·이머징 부담, 약달러 시 위험자산 선호.",
    },
    "^TNX": {
        "name_kr": "미 10년물 금리",
        "unit": "%",
        "desc": "장기 금리. 상승 시 성장주(바이오·플랫폼) 밸류에이션 압박, 하락 시 성장주 우호적.",
    },
    "CL=F": {
        "name_kr": "WTI 유가",
        "unit": "$/배럴",
        "desc": "에너지 비용. 급등 시 인플레 우려, 급락 시 수요 둔화 우려.",
    },
    "^GSPC": {
        "name_kr": "S&P 500",
        "unit": "",
        "desc": "미국 대형주 전반의 방향성 지표.",
    },
    "^IXIC": {
        "name_kr": "NASDAQ",
        "unit": "",
        "desc": "기술주 중심 시장 전반의 방향성 지표.",
    },
    "GC=F": {
        "name_kr": "금 Gold",
        "unit": "$/oz",
        "desc": "대표 안전자산. 금값 상승 시 위험회피 심리 강화.",
    },
    "KRW=X": {
        "name_kr": "원달러 환율",
        "unit": "원",
        "desc": "원화 가치. 환율 상승(원화 약세) 시 수출주 수혜, 외국인 투자 매력 감소.",
    },
}


def fetch_market_indicators():
    """글로벌 시장 지표 8개: 당일값 + 3개월 전 값 + 트렌드 + 차트용 시계열"""
    print("\n[5/8] 글로벌 시장 지표 조회 중...")

    results = []
    tickers_list = list(INDICATORS.keys())

    data = yf.download(tickers_list, period="4mo", group_by="ticker", threads=True)

    for ticker_sym, meta in INDICATORS.items():
        try:
            ticker_data = data[ticker_sym] if len(tickers_list) > 1 else data
            ticker_data = ticker_data.dropna(subset=["Close"])

            if ticker_data.empty:
                continue

            current = float(ticker_data["Close"].iloc[-1])
            period_ago = float(ticker_data["Close"].iloc[0])
            change_pct = ((current - period_ago) / period_ago) * 100

            # 최근 5일 평균 vs 이전 5일 평균 (단기 모멘텀)
            if len(ticker_data) >= 10:
                recent_5d = float(ticker_data["Close"].iloc[-5:].mean())
                prior_5d = float(ticker_data["Close"].iloc[-10:-5].mean())
                short_trend_pct = ((recent_5d - prior_5d) / prior_5d) * 100
            else:
                short_trend_pct = 0

            # 3개월 최고/최저
            period_high = float(ticker_data["High"].max())
            period_low = float(ticker_data["Low"].min())

            # 차트용 시계열 데이터 (종가 리스트)
            history_closes = [float(v) for v in ticker_data["Close"].tolist()]

            commentary = _build_indicator_commentary(
                ticker_sym, meta, current, period_ago, change_pct,
                short_trend_pct, period_high, period_low,
            )

            results.append({
                "ticker": ticker_sym,
                "name_kr": meta["name_kr"],
                "unit": meta["unit"],
                "desc": meta["desc"],
                "current": current,
                "period_ago": period_ago,
                "change_pct": change_pct,
                "short_trend_pct": short_trend_pct,
                "period_high": period_high,
                "period_low": period_low,
                "commentary": commentary,
                "history": history_closes,
            })
            print(f"  [OK] {meta['name_kr']}: {current:.2f} ({change_pct:+.1f}% 3M)")

        except Exception as e:
            print(f"  [FAIL] {meta['name_kr']}: {e}")

    return results


def _build_indicator_commentary(ticker, meta, current, period_ago, change_pct,
                                short_trend_pct, period_high, period_low):
    """지표별 한국어 코멘트 생성 (3개월 기준)"""
    name = meta["name_kr"]

    # 방향 텍스트
    if change_pct > 10:
        trend_3m = "3개월간 급등"
    elif change_pct > 3:
        trend_3m = "3개월간 상승 추세"
    elif change_pct > -3:
        trend_3m = "3개월간 보합 유지"
    elif change_pct > -10:
        trend_3m = "3개월간 하락 추세"
    else:
        trend_3m = "3개월간 급락"

    if short_trend_pct > 2:
        short = "최근 단기 반등 중"
    elif short_trend_pct < -2:
        short = "최근 단기 하락 중"
    else:
        short = "최근 횡보 중"

    # ── VIX ──
    if ticker == "^VIX":
        if current < 15:
            level = "극도의 안도감 구간 — 과열 경계 필요"
        elif current < 20:
            level = "안정 구간 — 시장 낙관적"
        elif current < 25:
            level = "불안감 상승 구간 — 변동성 확대 경계"
        elif current < 30:
            level = "공포 구간 — 헤지 수요 증가"
        else:
            level = "극도의 공포 — 패닉 매도 가능성"
        return (
            f"현재 {current:.1f}pt로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:.1f}~{period_high:.1f}."
        )

    # ── 미 10년물 금리 ──
    if ticker == "^TNX":
        if current > 4.5:
            level = "고금리 부담 구간 — 성장주(바이오·플랫폼) 밸류에이션 압박"
        elif current > 4.0:
            level = "중립~부담 구간 — 성장주 선별적 접근"
        elif current > 3.5:
            level = "완화적 구간 — 성장주 우호적"
        else:
            level = "저금리 — 위험자산 강한 우호"
        return (
            f"현재 {current:.2f}%로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:.2f}%~{period_high:.2f}%."
        )

    # ── 달러인덱스 ──
    if ticker == "DX-Y.NYB":
        if current > 105:
            level = "강달러 구간 — 이머징/수출주 부담"
        elif current > 100:
            level = "보통 수준"
        elif current > 95:
            level = "약달러 진입 — 위험자산 우호적"
        else:
            level = "약달러 구간 — 원자재/이머징 수혜"
        return (
            f"현재 {current:.1f}pt로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:.1f}~{period_high:.1f}."
        )

    # ── S&P 500 ──
    if ticker == "^GSPC":
        return (
            f"현재 {current:,.0f}pt. {trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:,.0f}~{period_high:,.0f}. "
            f"{'사상 최고가 근접 — 돌파 시 추가 모멘텀 기대.' if change_pct > 5 else '추세 전환 여부 주시 필요.'}"
        )

    # ── 나스닥 종합 ──
    if ticker == "^IXIC":
        return (
            f"현재 {current:,.0f}pt. {trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:,.0f}~{period_high:,.0f}. "
            f"{'사상 최고가 근접 — 돌파 시 추가 모멘텀 기대.' if change_pct > 5 else '추세 전환 여부 주시 필요.'}"
        )

    # ── WTI 원유 ──
    if ticker == "CL=F":
        if current > 80:
            level = "고유가 — 인플레 압력, 에너지주 수혜"
        elif current > 65:
            level = "적정 수준"
        else:
            level = "저유가 — 수요 둔화 우려, 소비주 수혜"
        return (
            f"현재 ${current:.1f}/배럴로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 ${period_low:.1f}~${period_high:.1f}."
        )

    # ── 금 Gold ──
    if ticker == "GC=F":
        if current > 2500:
            level = "고금값 — 안전자산 수요 강세"
        elif current > 2000:
            level = "보통 수준"
        else:
            level = "저금값 — 위험자산 선호"
        return (
            f"현재 ${current:,.1f}/oz로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 ${period_low:,.1f}~${period_high:,.1f}."
        )

    # ── 원달러 환율 ──
    if ticker == "KRW=X":
        if current > 1400:
            level = "원화 약세 — 수출주 실적 수혜, 외국인 매력 감소"
        elif current > 1300:
            level = "보통 수준"
        else:
            level = "원화 강세 — 외국인 자금 유입 기대"
        return (
            f"현재 {current:,.1f}원으로 {level}. "
            f"{trend_3m} ({change_pct:+.1f}%), {short}. "
            f"3개월 레인지 {period_low:,.1f}~{period_high:,.1f}원."
        )

    # 기본
    return f"현재 {current:.2f}. {trend_3m} ({change_pct:+.1f}%), {short}."


# ═══════════════════════════════════════════════════════════════
#  6. 뉴스 수집 (관련성 스코어링 + 중복 제거 + 한국어 번역)
# ═══════════════════════════════════════════════════════════════

def _title_similarity(a, b):
    """두 제목의 유사도 (0~1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_article(article, sector_tickers, sector_en):
    """뉴스 관련성 점수 (0~100)"""
    title_lower = article["title"].lower()
    score = 0

    # 1. 최신순 (pubDate 파싱)
    try:
        pub = article.get("pub_date", "")
        # RFC 2822 형식 파싱
        from email.utils import parsedate_to_datetime
        pub_dt = parsedate_to_datetime(pub)
        age_hours = (datetime.now(pub_dt.tzinfo) - pub_dt).total_seconds() / 3600
        if age_hours < 24:
            score += 30
        elif age_hours < 48:
            score += 22
        elif age_hours < 72:
            score += 15
        elif age_hours < 120:
            score += 8
    except Exception:
        score += 5  # 파싱 실패 시 중간값

    # 2. 기업명/티커 포함 여부
    ticker_matches = 0
    for t in sector_tickers:
        if t.lower() in title_lower or t.lower() in article.get("link", "").lower():
            ticker_matches += 1
    score += min(ticker_matches * 12, 25)

    # 3. 섹터 키워드 매칭
    sector_kw = {
        "Semiconductors": ["chip", "semiconductor", "memory", "ai chip", "hbm", "dram", "nand", "fab"],
        "Data Storage": ["storage", "nand", "flash", "ssd", "hdd", "memory"],
        "Software - Application": ["software", "saas", "cloud", "enterprise"],
        "Software - Infrastructure": ["cloud", "infrastructure", "cybersecurity", "devops"],
        "Internet Content & Information": ["google", "search", "youtube", "advertising", "ad revenue"],
        "Entertainment": ["streaming", "content", "subscriber", "netflix"],
        "Internet Retail": ["ecommerce", "retail", "amazon", "online shopping"],
        "Auto Manufacturers": ["ev", "tesla", "electric vehicle", "autonomous", "robotaxi"],
        "Electronic Gaming & Multimedia": ["gaming", "metaverse", "roblox"],
        "Capital Markets": ["fintech", "trading", "robinhood", "crypto", "bitcoin"],
    }
    keywords = sector_kw.get(sector_en, [sector_en.lower()])
    for kw in keywords:
        if kw in title_lower:
            score += 15
            break

    # 4. 출처 신뢰도 (주요 매체 가산)
    major = ["cnbc", "bloomberg", "reuters", "wsj", "wall street",
             "yahoo finance", "barron", "seeking alpha", "motley fool",
             "financial times", "marketwatch", "investor"]
    source_lower = article.get("source", "").lower()
    if any(s in source_lower for s in major):
        score += 10

    return score


def _extract_bing_url(bing_link):
    """Bing News 리다이렉트 URL → 실제 기사 URL 추출"""
    try:
        parsed = urlparse(bing_link)
        params = parse_qs(parsed.query)
        if "url" in params:
            return unquote(params["url"][0])
    except Exception:
        pass
    return bing_link


def _fetch_yahoo_finance_rss(tickers):
    """Yahoo Finance RSS: 티커 기반 뉴스 (직접 링크 제공)"""
    ticker_str = ",".join(tickers[:5])
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker_str}&region=US&lang=en-US"
    headers = {"User-Agent": "Mozilla/5.0"}
    articles = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item")[:15]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            # .tsrc=rss 제거
            link = link.split("?.tsrc")[0] if "?.tsrc" in link else link
            if title and link:
                articles.append({
                    "title": title, "link": link,
                    "pub_date": pub_date, "source": "Yahoo Finance",
                })
    except Exception:
        pass
    return articles


def _fetch_bing_news_rss(query):
    """Bing News RSS: 키워드 기반 뉴스 (직접 링크 추출)"""
    encoded = quote(query)
    url = f"https://www.bing.com/news/search?q={encoded}&format=rss&count=15&mkt=en-US"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    articles = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item")[:15]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            actual_url = _extract_bing_url(link)
            if title and actual_url:
                articles.append({
                    "title": title, "link": actual_url,
                    "pub_date": pub_date, "source": "Bing News",
                })
    except Exception:
        pass
    return articles


def fetch_sector_news(sector_en, sector_tickers, num_articles=3):
    """Yahoo Finance + Bing News → 관련성 스코어링 → 중복 제거 → 상위 N개"""

    # 소스 1: Yahoo Finance RSS (티커 기반, 직접 링크)
    raw_articles = _fetch_yahoo_finance_rss(sector_tickers)

    # 소스 2: Bing News RSS (키워드 기반, 보충)
    query = f"NASDAQ {sector_en} stocks {' '.join(sector_tickers[:3])}"
    raw_articles += _fetch_bing_news_rss(query)

    # 스코어링
    for a in raw_articles:
        a["score"] = _score_article(a, sector_tickers, sector_en)

    # 점수순 정렬
    raw_articles.sort(key=lambda x: x["score"], reverse=True)

    # 중복 제거 (제목 유사도 70% 이상이면 중복)
    selected = []
    for a in raw_articles:
        is_dup = False
        for s in selected:
            if _title_similarity(a["title"], s["title"]) > 0.7:
                is_dup = True
                break
        if not is_dup:
            selected.append(a)
        if len(selected) >= num_articles:
            break

    # 한국어 번역
    for a in selected:
        a["title_kr"] = translate_to_korean(a["title"])
        time.sleep(0.3)

    return selected


def collect_all_sector_news(sector_summary):
    """전체 섹터 뉴스 수집"""
    print("\n[6/8] 전체 섹터별 관련 뉴스 수집 중...")

    news_data = {}
    total = len(sector_summary)
    for idx, (sector_en, data) in enumerate(sector_summary.iterrows(), 1):
        kr = industry_to_kr(sector_en)
        tickers = data["tickers"]
        print(f"  [{idx}/{total}] {kr} ({sector_en}) 뉴스 검색 중...")
        articles = fetch_sector_news(sector_en, tickers, num_articles=3)
        news_data[sector_en] = articles
        if articles:
            for a in articles:
                print(f"    [{a['score']:2d}점] {a.get('title_kr', a['title'])[:55]}...")
        else:
            print(f"    (뉴스 없음)")
        time.sleep(0.5)

    return news_data


# ═══════════════════════════════════════════════════════════════
#  7. HTML 리포트 생성
# ═══════════════════════════════════════════════════════════════

def format_dollar(value):
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    elif value >= 1e6:
        return f"${value / 1e6:.1f}M"
    else:
        return f"${value:,.0f}"


def _change_pct_html(pct):
    """등락률을 색상이 적용된 HTML로 반환"""
    if pct > 0:
        return f'<span style="color:#e53935;font-weight:700;">+{pct:.2f}%</span>'
    elif pct < 0:
        return f'<span style="color:#1e88e5;font-weight:700;">{pct:.2f}%</span>'
    else:
        return f'<span style="color:#999;font-weight:700;">0.00%</span>'


# ── 트리맵 PNG 생성 (matplotlib → base64) ──

def _render_treemap_png(sector_summary, df):
    """섹터별 거래대금 분포 트리맵을 matplotlib로 생성, PNG bytes 반환"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib import font_manager
    from io import BytesIO

    # 한글 폰트 설정
    for fname in ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]:
        try:
            font_manager.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.family"] = fname
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    # 데이터 준비
    items = []
    colors = [
        "#1565c0", "#e65100", "#2e7d32", "#6a1b9a", "#c62828",
        "#00838f", "#d84315", "#388e3c", "#7b1fa2", "#283593",
        "#4e342e", "#546e7a", "#ad1457", "#00695c", "#4527a0",
        "#f9a825", "#558b2f", "#0277bd", "#880e4f", "#827717",
    ]

    for idx, (industry_en, sdata) in enumerate(sector_summary.iterrows()):
        kr = industry_to_kr(industry_en)
        vol = sdata["total_dollar_volume"]
        sector_stocks = df[df["industry"] == industry_en].sort_values("dollar_volume", ascending=False)
        top_ticker = sector_stocks.iloc[0]["ticker"] if not sector_stocks.empty else sdata["tickers"][0]
        items.append({
            "label": kr, "ticker": top_ticker, "value": vol,
            "color": colors[idx % len(colors)], "vol_str": format_dollar(vol),
        })

    total = sum(it["value"] for it in items)
    if total == 0:
        return None

    sorted_items = sorted(items, key=lambda x: x["value"], reverse=True)

    # slice-and-dice 레이아웃 계산
    def _layout(items_list, x, y, w, h, horizontal=True):
        rects = []
        total_val = sum(it["value"] for it in items_list)
        if total_val == 0 or not items_list:
            return rects
        pos = x if horizontal else y
        for it in items_list:
            ratio = it["value"] / total_val
            if horizontal:
                rw = w * ratio
                rects.append({"x": pos, "y": y, "w": rw, "h": h, **it})
                pos += rw
            else:
                rh = h * ratio
                rects.append({"x": x, "y": pos, "w": w, "h": rh, **it})
                pos += rh
        return rects

    # 2행 분할
    cumsum = 0
    split_idx = 0
    for i, it in enumerate(sorted_items):
        cumsum += it["value"]
        if cumsum >= total * 0.55:
            split_idx = i + 1
            break
    split_idx = max(1, split_idx or len(sorted_items) // 2)

    top_group = sorted_items[:split_idx]
    bot_group = sorted_items[split_idx:]
    top_val = sum(it["value"] for it in top_group)
    bot_val = sum(it["value"] for it in bot_group)
    fig_w, fig_h = 10, 5
    top_h_ratio = top_val / (top_val + bot_val) if (top_val + bot_val) > 0 else 0.5
    top_h = fig_h * top_h_ratio
    bot_h = fig_h - top_h

    rects = _layout(top_group, 0, 0, fig_w, top_h, horizontal=True)
    rects += _layout(bot_group, 0, top_h, fig_w, bot_h, horizontal=True)

    # matplotlib 그리기
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(fig_h, 0)  # y축 반전
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    for r in rects:
        rx, ry, rw, rh = r["x"], r["y"], r["w"], r["h"]
        rect = mpatches.FancyBboxPatch(
            (rx + 0.02, ry + 0.02), rw - 0.04, rh - 0.04,
            boxstyle="round,pad=0.02", facecolor=r["color"], edgecolor="white", linewidth=2,
        )
        ax.add_patch(rect)

        cx, cy = rx + rw / 2, ry + rh / 2
        area = rw * rh
        if area > 3:
            fs_l, fs_t, fs_v = 11, 14, 8
        elif area > 1:
            fs_l, fs_t, fs_v = 9, 11, 7
        elif area > 0.4:
            fs_l, fs_t, fs_v = 7, 9, 0
        else:
            fs_l, fs_t, fs_v = 5, 7, 0

        if rw > 0.3 and rh > 0.3:
            ax.text(cx, cy - 0.18, r["label"], ha="center", va="center",
                    fontsize=fs_l, color="white", alpha=0.85, fontweight="normal")
            ax.text(cx, cy + 0.15, r["ticker"], ha="center", va="center",
                    fontsize=fs_t, color="white", fontweight="bold")
            if fs_v > 0 and rh > 0.9:
                ax.text(cx, cy + 0.45, r["vol_str"], ha="center", va="center",
                        fontsize=fs_v, color="white", alpha=0.7)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", pad_inches=0.02,
                facecolor="#1a1a2e", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── 지표 차트 PNG 생성 (2x4 그리드, matplotlib → bytes) ──

def _render_indicator_charts_png(indicators):
    """8개 지표 3개월 차트를 2x4 그리드 PNG로 생성, PNG bytes 반환"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np
    from io import BytesIO

    if not indicators:
        return None

    # 한글 폰트 설정
    for fname in ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]:
        try:
            font_manager.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.family"] = fname
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    cols = 2
    rows = math.ceil(len(indicators) / cols)

    bg_colors = [
        "#1a237e", "#e65100", "#1b5e20", "#4a148c",
        "#b71c1c", "#004d40", "#bf360c", "#263238",
    ]

    fig, axes = plt.subplots(rows, cols, figsize=(10, rows * 2.2))
    fig.patch.set_facecolor("#1a1a2e")
    if rows == 1:
        axes = [axes]
    axes_flat = [ax for row_axes in axes for ax in (row_axes if hasattr(row_axes, '__len__') else [row_axes])]

    for i, ind in enumerate(indicators):
        ax = axes_flat[i]
        bg = bg_colors[i % len(bg_colors)]
        history = ind.get("history", [])
        pct = ind["change_pct"]
        name = ind["name_kr"]

        ax.set_facecolor(bg)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        # 현재값 포맷
        unit = ind["unit"]
        if unit == "%":
            val_fmt = f'{ind["current"]:.2f}%'
        elif unit == "$/배럴":
            val_fmt = f'${ind["current"]:.1f}'
        elif unit == "$/oz":
            val_fmt = f'${ind["current"]:,.0f}'
        elif unit == "원":
            val_fmt = f'{ind["current"]:,.0f}원'
        elif ind["ticker"] in ("^GSPC", "^IXIC"):
            val_fmt = f'{ind["current"]:,.0f}'
        else:
            val_fmt = f'{ind["current"]:.2f}'

        arrow = "▲" if pct > 0.3 else ("▼" if pct < -0.3 else "―")
        pct_color = "#ff8a80" if pct > 0.3 else ("#82b1ff" if pct < -0.3 else "#e0e0e0")
        line_color = "#ff8a80" if pct > 0.3 else ("#82b1ff" if pct < -0.3 else "#e0e0e0")

        # 라인 차트
        if len(history) >= 2:
            x = np.arange(len(history))
            y = np.array(history)
            ax.plot(x, y, color=line_color, linewidth=1.5, zorder=3)
            ax.fill_between(x, y, y.min(), color=line_color, alpha=0.15, zorder=2)
            ax.scatter([x[-1]], [y[-1]], color=line_color, s=20, zorder=4)

            # 최저/최고 라벨
            ax.text(0.01, 0.02, f'{y.min():,.2f}', transform=ax.transAxes,
                    fontsize=6, color="white", alpha=0.5, va="bottom")
            ax.text(0.99, 0.02, f'{y.max():,.2f}', transform=ax.transAxes,
                    fontsize=6, color="white", alpha=0.5, va="bottom", ha="right")

        # 지표명 (좌상단)
        ax.text(0.03, 0.92, name, transform=ax.transAxes,
                fontsize=9, color="white", alpha=0.8, va="top", fontweight="normal")
        # 현재값 (우상단)
        ax.text(0.97, 0.92, val_fmt, transform=ax.transAxes,
                fontsize=11, color="white", va="top", ha="right", fontweight="bold")
        # 변동률 (우측 2번째 줄)
        ax.text(0.97, 0.76, f'{arrow} {pct:+.1f}% (3M)', transform=ax.transAxes,
                fontsize=7, color=pct_color, va="top", ha="right")

    # 빈 셀 숨기기
    for j in range(len(indicators), len(axes_flat)):
        axes_flat[j].set_visible(False)

    plt.tight_layout(pad=0.3, h_pad=0.4, w_pad=0.4)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", pad_inches=0.05,
                facecolor="#1a1a2e", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def build_html_report(df, sector_summary, news_data, indicators):
    today_str = datetime.now().strftime("%Y-%m-%d")
    total_volume = df["dollar_volume"].sum()
    total_vol_str = format_dollar(total_volume)

    # 섹터별 색상
    sector_colors = [
        "#2979ff", "#ff6d00", "#00c853", "#aa00ff", "#e53935",
        "#00bcd4", "#ff5722", "#4caf50", "#9c27b0", "#3f51b5",
        "#795548", "#607d8b", "#f44336", "#009688", "#673ab7",
        "#ffc107", "#8bc34a", "#03a9f4", "#e91e63", "#cddc39",
    ]

    # 트리맵 / 지표차트 PNG 바이너리 생성
    treemap_png = _render_treemap_png(sector_summary, df)
    indicator_png = _render_indicator_charts_png(indicators)
    # CID 참조용 (이메일) + base64 인라인 (로컬 HTML) 동시 지원
    # HTML에는 cid: 를 사용하고, 로컬 저장용 HTML에는 base64 폴백
    import base64 as _b64
    treemap_img = ""
    indicator_charts_img = ""
    if treemap_png:
        treemap_b64 = _b64.b64encode(treemap_png).decode("ascii")
        treemap_img = f'<img src="cid:treemap_chart" style="width:100%;max-width:960px;border-radius:8px;" alt="섹터별 거래대금 트리맵">'
    if indicator_png:
        indicator_b64 = _b64.b64encode(indicator_png).decode("ascii")
        indicator_charts_img = f'<img src="cid:indicator_chart" style="width:100%;max-width:960px;border-radius:8px;" alt="글로벌 시장 지표 차트">'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; background: #f0f2f5; padding: 20px; color: #333; line-height: 1.6; }}
  .container {{ max-width: 960px; margin: 0 auto; background: #fff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
  .header {{ background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%); color: #fff; padding: 36px 32px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 24px; letter-spacing: -0.5px; }}
  .header .subtitle {{ margin: 8px 0 0; opacity: 0.7; font-size: 13px; }}
  .summary-bar {{ display: flex; justify-content: center; gap: 32px; margin-top: 16px; }}
  .summary-item {{ text-align: center; }}
  .summary-item .val {{ font-size: 20px; font-weight: 700; }}
  .summary-item .lbl {{ font-size: 11px; opacity: 0.65; }}
  .section {{ padding: 28px 32px; }}
  .section-title {{ font-size: 16px; color: #1a1a2e; padding-bottom: 10px; margin: 0 0 18px; letter-spacing: -0.3px; display: flex; align-items: center; gap: 8px; border-bottom: 2px solid #e8e8e8; }}
  .section-title .icon {{ font-size: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{ background: #f8f9fb; padding: 10px 8px; text-align: left; font-weight: 600; border-bottom: 2px solid #dee2e6; font-size: 11.5px; color: #555; }}
  td {{ padding: 9px 8px; border-bottom: 1px solid #f0f0f0; }}
  tr:hover {{ background: #fafbfc; }}
  .tag-ath {{ background: #e53935; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 10.5px; font-weight: 600; white-space: nowrap; }}
  .tag-near {{ background: #fb8c00; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 10.5px; font-weight: 600; white-space: nowrap; }}
  .sector-block {{ background: #fff; border: 1px solid #e8e8e8; border-radius: 10px; padding: 20px; margin-bottom: 20px; }}
  .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
  .sector-header h3 {{ margin: 0; font-size: 15px; color: #1a1a2e; display: flex; align-items: center; gap: 8px; }}
  .sector-header h3 .bar {{ display: inline-block; width: 4px; height: 18px; border-radius: 2px; }}
  .sector-header .sector-vol {{ font-size: 15px; font-weight: 700; color: #555; }}
  .sector-meta {{ font-size: 11px; color: #999; margin-bottom: 12px; }}
  .news-block {{ margin-top: 10px; }}
  .news-block-title {{ font-size: 12px; color: #555; font-weight: 600; margin-bottom: 6px; }}
  .news-item {{ padding: 6px 0; border-bottom: 1px solid #f0f0f0; }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-item a {{ color: #1565c0; text-decoration: none; font-weight: 500; font-size: 13px; }}
  .news-item a:hover {{ text-decoration: underline; }}
  .news-source {{ font-size: 10px; color: #aaa; margin-right: 6px; background: #f0f0f0; padding: 1px 6px; border-radius: 3px; }}
  .footer {{ text-align: center; padding: 22px; font-size: 11px; color: #aaa; background: #f8f9fb; }}
  .dollar-vol {{ text-align: right; font-family: 'SF Mono', 'Courier New', monospace; font-size: 12px; }}
  .price {{ text-align: right; font-family: 'SF Mono', 'Courier New', monospace; font-size: 12px; }}
  .indicator-table th {{ font-size: 11.5px; }}
  .indicator-table td {{ font-size: 12px; vertical-align: top; }}
  .indicator-table .commentary {{ font-size: 11.5px; color: #555; line-height: 1.5; max-width: 420px; }}
  .treemap-section {{ padding: 20px 32px 10px; }}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>[{today_str}] NASDAQ 일일 브리핑 &mdash; 거래대금 상위 30</h1>
  <div class="subtitle">{today_str} | 거래대금 상위 30개 종목 | 전체 {len(sector_summary)}개 섹터</div>
  <div class="summary-bar">
    <div class="summary-item"><div class="val">{total_vol_str}</div><div class="lbl">총 거래대금</div></div>
    <div class="summary-item"><div class="val">{len(df[df['ath_tag'] != ''])}개</div><div class="lbl">신고가 관련</div></div>
    <div class="summary-item"><div class="val">{len(sector_summary)}개</div><div class="lbl">섹터</div></div>
  </div>
</div>
"""

    # ── (treemap) 섹터별 거래대금 분포 트리맵 ──
    if treemap_img:
        html += f"""
<div class="treemap-section">
  <div class="section-title"><span class="icon">📊</span> 섹터별 거래대금 분포</div>
  {treemap_img}
</div>
"""

    # ── (a) 거래대금 순위 TOP 30 테이블 ──
    html += """
<div class="section">
  <div class="section-title"><span class="icon">📈</span> 거래대금 순위 TOP 30</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>종목명</th>
        <th>섹터</th>
        <th style="text-align:right">거래대금</th>
        <th style="text-align:right">등락률</th>
        <th>태그</th>
      </tr>
    </thead>
    <tbody>
"""
    for i, row in df.iterrows():
        tag_html = ""
        if row["ath_tag"] == "[신고가 돌파]":
            tag_html = '<span class="tag-ath">🏷 신고가 돌파</span>'
        elif row["ath_tag"] == "[신고가 접근중]":
            tag_html = '<span class="tag-near">📊 신고가 접근중</span>'

        chg_html = _change_pct_html(row["change_pct"])
        name_display = f"{row['ticker']}  {row['name'][:24]}"

        html += f"""      <tr>
        <td>{i+1}</td>
        <td><strong>{name_display}</strong></td>
        <td>{row['industry_kr']}</td>
        <td class="dollar-vol">{format_dollar(row['dollar_volume'])}</td>
        <td style="text-align:right">{chg_html}</td>
        <td>{tag_html}</td>
      </tr>
"""

    html += "    </tbody>\n  </table>\n</div>\n"

    # ── (b) 전체 섹터 상세 섹션 (거래대금 순, PDF 스타일) ──
    sector_colors_list = [
        "#1565c0", "#e65100", "#2e7d32", "#6a1b9a", "#c62828",
        "#00838f", "#d84315", "#388e3c", "#7b1fa2", "#283593",
        "#4e342e", "#37474f", "#ad1457", "#00695c", "#4527a0",
        "#f9a825", "#558b2f", "#0277bd", "#880e4f", "#9e9d24",
    ]

    for rank, (industry_en, sdata) in enumerate(sector_summary.iterrows(), 1):
        kr = industry_to_kr(industry_en)
        parent = sector_to_kr(sdata["sector"])
        vol_str = format_dollar(sdata["total_dollar_volume"])
        color = sector_colors_list[(rank - 1) % len(sector_colors_list)]

        html += f"""
<div class="section" style="padding-bottom:8px;padding-top:20px;">
  <div class="sector-block">
    <div class="sector-header">
      <h3><span class="bar" style="background:{color};"></span> {kr}</h3>
      <span class="sector-vol">총 {vol_str}</span>
    </div>
    <div class="sector-meta">대분류: {parent} | {int(sdata['stock_count'])}개 종목</div>
"""

        # 섹터 내 종목 상세 테이블
        sector_stocks = df[df["industry"] == industry_en]
        if not sector_stocks.empty:
            html += """    <table style="margin-bottom:10px;">
      <thead>
        <tr>
          <th>종목명</th>
          <th style="text-align:right">거래대금</th>
          <th style="text-align:right">등락률</th>
          <th style="text-align:right">종가</th>
          <th style="text-align:right">52주고가</th>
          <th>태그</th>
        </tr>
      </thead>
      <tbody>
"""
            for _, srow in sector_stocks.iterrows():
                stag = ""
                if srow["ath_tag"] == "[신고가 돌파]":
                    stag = '<span class="tag-ath">돌파</span>'
                elif srow["ath_tag"] == "[신고가 접근중]":
                    stag = '<span class="tag-near">근접</span>'

                ath_price_str = f"${srow['all_time_high']:,.2f}" if srow["all_time_high"] > 0 else "-"
                chg_html = _change_pct_html(srow["change_pct"])

                html += f"""        <tr>
          <td><strong>{srow['ticker']}</strong> {srow['name'][:22]}</td>
          <td class="dollar-vol">{format_dollar(srow['dollar_volume'])}</td>
          <td style="text-align:right">{chg_html}</td>
          <td class="price">${srow['close']:,.2f}</td>
          <td class="price">{ath_price_str}</td>
          <td>{stag}</td>
        </tr>
"""
            html += "      </tbody>\n    </table>\n"

        # 관련 뉴스 (3건)
        articles = news_data.get(industry_en, [])
        if articles:
            html += '    <div class="news-block">\n'
            html += f'      <div class="news-block-title">관련 뉴스 ({len(articles)}건)</div>\n'
            for article in articles:
                source_name = article.get("source", "")
                title_kr = article.get("title_kr", article["title"])
                html += f"""      <div class="news-item">
        <span class="news-source">{source_name}</span>
        <a href="{article['link']}" target="_blank">{title_kr}</a>
      </div>
"""
            html += "    </div>\n"

        html += "  </div>\n</div>\n"

    # ── (c) 글로벌 시장 지표: 차트 + 해석 테이블 ──
    if indicators:
        # 차트 섹션
        html += f"""
<div class="section">
  <div class="section-title"><span class="icon">🌐</span> 글로벌 시장 지표 (최근 3개월)</div>
  {indicator_charts_img}
</div>
"""
        # 지표별 해석 테이블
        html += """
<div class="section" style="padding-top:0;">
  <div class="section-title">지표별 해석</div>
  <table class="indicator-table">
    <thead>
      <tr>
        <th>지표</th>
        <th style="text-align:right">현재값</th>
        <th style="text-align:right">3개월변화</th>
        <th>해석</th>
      </tr>
    </thead>
    <tbody>
"""
        for ind in indicators:
            pct = ind["change_pct"]
            if abs(pct) < 3:
                emoji = "🟡"
            elif pct > 0:
                emoji = "📈"
            else:
                emoji = "📉"

            unit = ind["unit"]
            if unit == "%":
                val_fmt = f"{ind['current']:.2f}%"
            elif unit == "$/배럴":
                val_fmt = f"${ind['current']:.1f}"
            elif unit == "$/oz":
                val_fmt = f"${ind['current']:,.1f}"
            elif unit == "원":
                val_fmt = f"{ind['current']:,.1f}원"
            elif ind["ticker"] in ("^GSPC", "^IXIC"):
                val_fmt = f"{ind['current']:,.0f}"
            else:
                val_fmt = f"{ind['current']:.2f}"

            chg_color = "#e53935" if pct > 0.5 else ("#1e88e5" if pct < -0.5 else "#999")

            html += f"""      <tr>
        <td>{emoji} {ind['name_kr']}</td>
        <td style="text-align:right; font-weight:700;">{val_fmt}</td>
        <td style="text-align:right; color:{chg_color}; font-weight:600;">{pct:+.1f}%</td>
        <td class="commentary">{ind['commentary']}</td>
      </tr>
"""

        html += """    </tbody>
  </table>
  <div style="margin-top:12px;padding:10px;background:#fff8e1;border-radius:6px;font-size:11px;color:#795548;">
    ⚠️ 위 지표들은 비교적 글로벌 매크로 흐름을 읽기위한, 매크로 수급 시나리오 연계에 특히 유용합니다.
  </div>
</div>
"""

    # ── (d) Footer ──
    html += f"""
<div class="footer">
  본 메일은 자동으로 발송되었습니다. 투자 판단은 본인 책임입니다.
</div>

</div>
</body>
</html>"""

    # 로컬 HTML 파일용: cid: → base64 인라인으로 대체한 버전
    html_local = html
    if treemap_png:
        html_local = html_local.replace(
            'src="cid:treemap_chart"',
            f'src="data:image/png;base64,{treemap_b64}"'
        )
    if indicator_png:
        html_local = html_local.replace(
            'src="cid:indicator_chart"',
            f'src="data:image/png;base64,{indicator_b64}"'
        )

    # 이미지 데이터를 딕셔너리로 함께 반환
    images = {}
    if treemap_png:
        images["treemap_chart"] = treemap_png
    if indicator_png:
        images["indicator_chart"] = indicator_png

    return html, html_local, images


# ═══════════════════════════════════════════════════════════════
#  이메일 발송
# ═══════════════════════════════════════════════════════════════

def send_email(html_content, recipients, smtp_user, smtp_password, images=None):
    """HTML 이메일 발송 (CID 이미지 첨부, 복수 수신자 지원)"""
    from email.mime.image import MIMEImage

    # 복수 수신자 처리: 콤마 구분 문자열 또는 리스트
    if isinstance(recipients, str):
        recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
    else:
        recipient_list = list(recipients)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # related: HTML + 인라인 이미지를 묶는 컨테이너
    msg = MIMEMultipart("related")
    msg["Subject"] = f"[{today_str}] NASDAQ 일일 브리핑 — 거래대금 상위 30"
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipient_list)

    # alternative: text + html
    msg_alt = MIMEMultipart("alternative")
    msg.attach(msg_alt)

    text_part = MIMEText("HTML 지원 메일 앱에서 확인해주세요.", "plain", "utf-8")
    html_part = MIMEText(html_content, "html", "utf-8")
    msg_alt.attach(text_part)
    msg_alt.attach(html_part)

    # CID 이미지 첨부
    if images:
        for cid_name, img_bytes in images.items():
            img_part = MIMEImage(img_bytes, _subtype="png")
            img_part.add_header("Content-ID", f"<{cid_name}>")
            img_part.add_header("Content-Disposition", "inline", filename=f"{cid_name}.png")
            msg.attach(img_part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipient_list, msg.as_string())
        print(f"  [OK] 이메일 발송 완료 → {', '.join(recipient_list)}")
        return True
    except Exception as e:
        print(f"  [FAIL] 이메일 발송 실패: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  콘솔 출력
# ═══════════════════════════════════════════════════════════════

def print_results(df, sector_summary, news_data, indicators):
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 지표 출력
    if indicators:
        print("\n" + "=" * 110)
        print("  글로벌 시장 지표 (최근 3개월)")
        print("=" * 110)
        for ind in indicators:
            pct = ind["change_pct"]
            arrow = "▲" if pct > 0.5 else ("▼" if pct < -0.5 else "―")
            print(f"\n  {ind['name_kr']}")
            print(f"    현재: {ind['current']:.2f}  |  3개월전: {ind['period_ago']:.2f}  |  {arrow} {pct:+.1f}%")
            print(f"    {ind['commentary']}")

    print("\n" + "=" * 110)
    print(f"  NASDAQ 거래대금 Top 30  |  {today_str}")
    print("=" * 110)

    header = f"{'#':<4}{'Ticker':<8}{'종목명':<28}{'종가':>10}{'등락률':>10}{'거래대금':>15}{'세분화 섹터':<24}{'태그'}"
    print(f"\n{header}")
    print("-" * 115)

    for i, row in df.iterrows():
        chg_str = f"{row['change_pct']:+.2f}%"
        print(
            f"{i+1:<4}{row['ticker']:<8}{row['name'][:26]:<28}"
            f"${row['close']:>8.2f}{chg_str:>10}{format_dollar(row['dollar_volume']):>15}  "
            f"{row['industry_kr'][:22]:<24}{row['ath_tag']}"
        )

    print("\n" + "=" * 110)
    print("  전체 섹터별 자금 유입 분석")
    print("=" * 110)

    for rank, (industry_en, data) in enumerate(sector_summary.iterrows(), 1):
        kr = industry_to_kr(industry_en)
        parent = sector_to_kr(data["sector"])
        tickers_str = ", ".join(data["tickers"])
        print(f"\n  #{rank}  {kr} (대분류: {parent})")
        print(f"      총 거래대금: {format_dollar(data['total_dollar_volume'])}")
        print(f"      종목 수: {int(data['stock_count'])}개  |  종목: {tickers_str}")

        articles = news_data.get(industry_en, [])
        if articles:
            print(f"      --- 관련 뉴스 ---")
            for j, a in enumerate(articles, 1):
                print(f"      {j}. [{a.get('score',0)}점] {a.get('title_kr', a['title'])[:65]}")
                print(f"         원문: {a['title'][:65]}")
                print(f"         {a['link']}")

    ath_stocks = df[df["ath_tag"] != ""]
    if not ath_stocks.empty:
        print("\n" + "=" * 110)
        print("  신고가 관련 종목")
        print("=" * 110)
        for _, row in ath_stocks.iterrows():
            ath_pct = f" (ATH {row['close']/row['all_time_high']*100:.1f}%)" if row["all_time_high"] > 0 else ""
            print(f"  {row['ath_tag']:<16} {row['ticker']:<8}{row['name'][:25]:<26} ${row['close']:.2f}{ath_pct}")

    print("\n" + "=" * 110)


# ═══════════════════════════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 110)
    print("  NASDAQ 거래대금 Top 30 분석기 v3")
    print("=" * 110)

    # ── 환경변수 우선, 없으면 대화형 입력 (GitHub Actions 호환) ──
    GMAIL_USER = os.environ.get("GMAIL_USER", "")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
    RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "qkrwltn28@gmail.com,chelseaj960126@gmail.com")
    CI_MODE = bool(GMAIL_USER and GMAIL_APP_PASSWORD)

    if CI_MODE:
        print(f"  [CI] 환경변수 감지 — 자동 모드 (수신: {RECIPIENT})")

    # 1. 티커 수집
    tickers = collect_nasdaq_tickers()

    # 2. 시장 데이터 (등락률 포함)
    df = download_market_data(tickers)
    if df.empty:
        print("\n  [ERROR] 데이터를 가져올 수 없습니다.")
        return None, None

    # 3. 종목 상세 (세분화 섹터, 신고가)
    df = enrich_stock_info(df)

    # 4. 섹터 분석
    sector_summary = analyze_sectors(df)

    # 5. 글로벌 시장 지표
    indicators = fetch_market_indicators()

    # 6. 뉴스 수집 (전체 섹터)
    news_data = collect_all_sector_news(sector_summary)

    # 7. 콘솔 출력
    print("\n[7/8] 콘솔 결과 출력...")
    print_results(df, sector_summary, news_data, indicators)

    # 8. 리포트 생성 & 저장
    print("\n[8/8] 리포트 생성 및 저장 중...")
    today_tag = datetime.now().strftime("%Y%m%d")
    html_email, html_local, images = build_html_report(df, sector_summary, news_data, indicators)

    html_path = f"nasdaq_report_{today_tag}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_local)  # 로컬 파일은 base64 인라인 이미지 버전
    print(f"  [OK] {html_path} 저장 완료")

    csv_path = f"nasdaq_top30_{today_tag}.csv"
    save_cols = [
        "ticker", "name", "close", "volume", "dollar_volume",
        "prev_close", "change_pct",
        "sector", "sector_kr", "industry", "industry_kr", "ath_tag", "all_time_high",
    ]
    df[save_cols].to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {csv_path} 저장 완료")

    # ── 이메일 발송 ──
    print("\n" + "-" * 60)
    print("  이메일 발송")
    print("-" * 60)

    if CI_MODE:
        # GitHub Actions / 환경변수 모드: 자동 발송 (CID 이미지 첨부)
        send_email(html_email, RECIPIENT, GMAIL_USER, GMAIL_APP_PASSWORD, images)
    else:
        # 로컬 대화형 모드
        smtp_user = input("  Gmail 주소 (건너뛰려면 Enter): ").strip()
        if smtp_user:
            smtp_password = input("  앱 비밀번호 (16자리): ").strip()
            if smtp_password:
                send_email(html_email, RECIPIENT, smtp_user, smtp_password, images)
            else:
                print("  [SKIP] 비밀번호 미입력")
        else:
            print("  [SKIP] 이메일 건너뜀")
            print(f"  HTML 리포트: {html_path}")

    return df, sector_summary


if __name__ == "__main__":
    main()
