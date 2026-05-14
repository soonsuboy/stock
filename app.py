# -*- coding: utf-8 -*-
"""
한국/미국 상장사 투자지표 분석 웹앱
- FinanceDataReader + OpenDartReader + yfinance
- PER / PBR / ROE + 확장 지표
- SQLite 이력 저장
- 삼각형 다이어그램 (USD/KRW 병기)
"""
import os
import sqlite3
from datetime import datetime, date

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

import FinanceDataReader as fdr
try:
    from opendartreader import OpenDartReader
except ImportError:
    import OpenDartReader as _odr_module
    OpenDartReader = _odr_module.OpenDartReader if hasattr(_odr_module, "OpenDartReader") else _odr_module
    
import yfinance as yf

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="투자지표 분석기",
    page_icon="📊",
    layout="wide",
)

# ============================================================
# 한글 폰트 (Streamlit Cloud = Ubuntu, NanumGothic 사용)
# ============================================================
def setup_font():
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            plt.rcParams["font.family"] = "NanumGothic"
            break
    plt.rcParams["axes.unicode_minus"] = False

setup_font()

# ============================================================
# 비밀 키 (Streamlit Secrets 또는 환경변수)
# ============================================================
def get_dart_key():
    # 1) Streamlit Secrets
    try:
        if "DART_API_KEY" in st.secrets:
            return st.secrets["DART_API_KEY"]
    except Exception:
        pass
    # 2) 환경변수
    return os.environ.get("DART_API_KEY", "")

DB_PATH = os.environ.get("DB_PATH", "investment_metrics.db")

# ============================================================
# DB 초기화
# ============================================================
def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        code        TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        market      TEXT,
        country     TEXT,
        updated_at  TEXT
    );
    CREATE TABLE IF NOT EXISTS metrics_history (
        snapshot_date     TEXT NOT NULL,
        code              TEXT NOT NULL,
        name              TEXT,
        currency          TEXT,
        close_price       REAL,
        market_cap        REAL,
        equity            REAL,
        net_income        REAL,
        operating_income  REAL,
        total_liabilities REAL,
        debt_ratio        REAL,
        foreign_ratio     REAL,
        institution_ratio REAL,
        per               REAL,
        pbr               REAL,
        roe               REAL,
        report_code       TEXT,
        bsns_year         TEXT,
        source            TEXT,
        created_at        TEXT,
        PRIMARY KEY (snapshot_date, code)
    );
    """)
    conn.commit()
    conn.close()

init_db()

# ============================================================
# 종목 검색 (캐시)
# ============================================================
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_listings(market: str) -> pd.DataFrame:
    return fdr.StockListing(market)

@st.cache_data(ttl=3600, show_spinner=False)
def search_stock(keyword: str, top_n: int = 20) -> pd.DataFrame:
    keyword = keyword.strip()
    if not keyword:
        return pd.DataFrame()
    frames = []

    # KRX
    try:
        kr = get_listings("KRX").copy()
        code_col = "Code" if "Code" in kr.columns else "Symbol"
        kr = kr.rename(columns={code_col: "code", "Name": "name"})
        if "Market" in kr.columns:
            kr = kr.rename(columns={"Market": "market"})
        else:
            kr["market"] = "KRX"
        kr["country"] = "KR"
        mask = (
            kr["code"].astype(str).str.contains(keyword, case=False, na=False)
            | kr["name"].astype(str).str.contains(keyword, case=False, na=False)
        )
        frames.append(kr.loc[mask, ["code", "name", "market", "country"]])
    except Exception as e:
        st.warning(f"KRX 목록 조회 실패: {e}")

    # 미국
    for us_market in ["NASDAQ", "NYSE"]:
        try:
            us = get_listings(us_market).copy()
            sym_col = "Symbol" if "Symbol" in us.columns else "Code"
            us = us.rename(columns={sym_col: "code", "Name": "name"})
            us["market"] = us_market
            us["country"] = "US"
            mask = (
                us["code"].astype(str).str.contains(keyword, case=False, na=False)
                | us["name"].astype(str).str.contains(keyword, case=False, na=False)
            )
            frames.append(us.loc[mask, ["code", "name", "market", "country"]])
        except Exception as e:
            st.warning(f"{us_market} 목록 조회 실패: {e}")

    if not frames:
        return pd.DataFrame()
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["code"])
        .head(top_n)
        .reset_index(drop=True)
    )

# ============================================================
# 환율
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_usd_krw() -> float:
    try:
        fx = fdr.DataReader("USD/KRW")
        return float(fx["Close"].iloc[-1])
    except Exception:
        return 1400.0

# ============================================================
# 시세 수집
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_market_data(code: str, country: str = "KR") -> dict:
    result = {"close_price": None, "market_cap": None}
    if country == "KR":
        try:
            df = fdr.DataReader(code)
            if not df.empty:
                result["close_price"] = float(df["Close"].iloc[-1])
        except Exception as e:
            st.warning(f"{code} 종가 조회 실패: {e}")
        try:
            kr = get_listings("KRX")
            code_col = "Code" if "Code" in kr.columns else "Symbol"
            row = kr[kr[code_col] == code]
            if not row.empty and "Marcap" in row.columns:
                result["market_cap"] = float(row["Marcap"].iloc[0])
        except Exception as e:
            st.warning(f"{code} 시가총액 조회 실패: {e}")
    else:  # US
        try:
            tk = yf.Ticker(code)
            info = tk.info
            result["close_price"] = info.get("currentPrice") or info.get("previousClose")
            result["market_cap"] = info.get("marketCap")
        except Exception as e:
            st.warning(f"{code} 미국 시세 조회 실패: {e}")
    return result

# ============================================================
# DART 재무
# ============================================================
REPORT_CODES = [
    ("11011", "사업보고서"),
    ("11014", "3분기보고서"),
    ("11012", "반기보고서"),
    ("11013", "1분기보고서"),
]
ACCOUNT_PATTERNS = {
    "equity":            ["자본총계"],
    "net_income":        ["당기순이익", "당기순이익(손실)", "연결당기순이익"],
    "operating_income":  ["영업이익", "영업이익(손실)"],
    "total_liabilities": ["부채총계"],
}

def _to_number(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dart_financials(code: str, dart_key: str, year: int = None) -> dict:
    if not dart_key:
        return {"equity": None, "net_income": None, "operating_income": None,
                "total_liabilities": None, "bsns_year": None, "report_code": None,
                "source": "no_key"}
    if year is None:
        year = datetime.now().year
    dart = OpenDartReader(dart_key)
    out = {"equity": None, "net_income": None, "operating_income": None,
           "total_liabilities": None, "bsns_year": None, "report_code": None,
           "source": None}

    for try_year in [year, year - 1]:
        for rcode, rname in REPORT_CODES:
            df = None
            for fs_div in ["CFS", "OFS"]:
                try:
                    tmp = dart.finstate_all(code, try_year, reprt_code=rcode, fs_div=fs_div)
                    if tmp is not None and not tmp.empty:
                        df = tmp
                        out["source"] = f"{fs_div}/{rname}"
                        break
                except Exception:
                    continue
            if df is None or df.empty:
                continue
            for key, patterns in ACCOUNT_PATTERNS.items():
                if out[key] is not None:
                    continue
                hit = df[df["account_nm"].isin(patterns)]
                if hit.empty:
                    for p in patterns:
                        hit = df[df["account_nm"].astype(str).str.contains(p, na=False)]
                        if not hit.empty:
                            break
                if not hit.empty:
                    out[key] = _to_number(hit["thstrm_amount"].iloc[0])
            out["bsns_year"] = str(try_year)
            out["report_code"] = rcode
            if out["equity"] is not None and out["net_income"] is not None:
                return out
    return out

# ============================================================
# 미국 재무 (yfinance fallback)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_us_financials(code: str) -> dict:
    out = {"equity": None, "net_income": None, "operating_income": None,
           "total_liabilities": None, "bsns_year": None, "report_code": None,
           "source": "yfinance"}
    try:
        tk = yf.Ticker(code)
        bs = tk.balance_sheet
        fs = tk.financials
        if bs is not None and not bs.empty:
            for k in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]:
                if k in bs.index:
                    out["equity"] = float(bs.loc[k].iloc[0]); break
            for k in ["Total Liabilities Net Minority Interest", "Total Liab"]:
                if k in bs.index:
                    out["total_liabilities"] = float(bs.loc[k].iloc[0]); break
        if fs is not None and not fs.empty:
            for k in ["Net Income", "Net Income Common Stockholders"]:
                if k in fs.index:
                    out["net_income"] = float(fs.loc[k].iloc[0]); break
            for k in ["Operating Income", "Operating Revenue"]:
                if k in fs.index:
                    out["operating_income"] = float(fs.loc[k].iloc[0]); break
    except Exception as e:
        st.warning(f"{code} 미국 재무 조회 실패: {e}")
    return out

# ============================================================
# 보유 비율
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ownership_ratios(code: str, country: str = "KR") -> dict:
    out = {"foreign_ratio": None, "institution_ratio": None}
    if country == "US":
        try:
            info = yf.Ticker(code).info
            inst = info.get("heldPercentInstitutions")
            if inst is not None:
                out["institution_ratio"] = float(inst) * 100
        except Exception:
            pass
    return out

# ============================================================
# 메인 분석
# ============================================================
def analyze_stock(code: str, dart_key: str, name=None, country="KR", market=None, save_db=True):
    today = date.today().isoformat()
    if name is None:
        found = search_stock(code, top_n=1)
        if not found.empty:
            name    = found["name"].iloc[0]
            country = found["country"].iloc[0]
            market  = found["market"].iloc[0]
        else:
            name = code

    md = fetch_market_data(code, country)
    if country == "KR":
        fin = fetch_dart_financials(code, dart_key)
    else:
        fin = fetch_us_financials(code)
    own = fetch_ownership_ratios(code, country)

    def safe_div(a, b):
        if a is None or b is None or b == 0:
            return None
        return a / b

    market_cap        = md.get("market_cap")
    equity            = fin.get("equity")
    net_income        = fin.get("net_income")
    total_liabilities = fin.get("total_liabilities")

    per = safe_div(market_cap, net_income)
    pbr = safe_div(market_cap, equity)
    roe = safe_div(net_income, equity)
    if roe is not None: roe *= 100
    debt_ratio = safe_div(total_liabilities, equity)
    if debt_ratio is not None: debt_ratio *= 100

    currency = "KRW" if country == "KR" else "USD"

    row = {
        "snapshot_date":     today,
        "code":              code,
        "name":              name,
        "currency":          currency,
        "close_price":       md.get("close_price"),
        "market_cap":        market_cap,
        "equity":            equity,
        "net_income":        net_income,
        "operating_income":  fin.get("operating_income"),
        "total_liabilities": total_liabilities,
        "debt_ratio":        debt_ratio,
        "foreign_ratio":     own.get("foreign_ratio"),
        "institution_ratio": own.get("institution_ratio"),
        "per":               per,
        "pbr":               pbr,
        "roe":               roe,
        "report_code":       fin.get("report_code"),
        "bsns_year":         fin.get("bsns_year"),
        "source":            fin.get("source"),
        "created_at":        datetime.now().isoformat(timespec="seconds"),
    }

    if save_db:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO companies(code, name, market, country, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                market=excluded.market,
                country=excluded.country,
                updated_at=excluded.updated_at
        """, (code, name, market, country, row["created_at"]))
        cols = list(row.keys())
        placeholders = ",".join(["?"] * len(cols))
        updates = ",".join([f"{c}=excluded.{c}" for c in cols if c not in ("snapshot_date", "code")])
        cur.execute(f"""
            INSERT INTO metrics_history({','.join(cols)})
            VALUES({placeholders})
            ON CONFLICT(snapshot_date, code) DO UPDATE SET {updates}
        """, [row[c] for c in cols])
        conn.commit()
        conn.close()
    return row

# ============================================================
# 표시 헬퍼
# ============================================================
def _human(n, currency="KRW"):
    if n is None or pd.isna(n):
        return "N/A"
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if currency == "USD":
        if n >= 1e12: return f"{sign}${n/1e12:,.2f}T"
        if n >= 1e9:  return f"{sign}${n/1e9:,.2f}B"
        if n >= 1e6:  return f"{sign}${n/1e6:,.2f}M"
        if n >= 1e3:  return f"{sign}${n/1e3:,.2f}K"
        return f"{sign}${n:,.2f}"
    else:
        if n >= 1e12: return f"{sign}{n/1e12:,.2f}조원"
        if n >= 1e8:  return f"{sign}{n/1e8:,.2f}억원"
        if n >= 1e4:  return f"{sign}{n/1e4:,.2f}만원"
        return f"{sign}{n:,.2f}원"

def _human_dual(n, currency="KRW", fx=None):
    if n is None or pd.isna(n):
        return "N/A"
    if currency == "USD" and fx:
        return f"{_human(n, 'USD')}\n({_human(n * fx, 'KRW')})"
    return _human(n, currency)

def fmt_ratio(v, suffix=""):
    if v is None or pd.isna(v):
        return "N/A"
    return f"{v:,.2f}{suffix}"

# ============================================================
# 삼각형 다이어그램
# ============================================================
def draw_triangle(market_cap, equity, net_income, per=None, pbr=None, roe=None,
                  title="투자지표 삼각형", currency="KRW"):
    if per is None and net_income not in (None, 0): per = market_cap / net_income
    if pbr is None and equity     not in (None, 0): pbr = market_cap / equity
    if roe is None and equity     not in (None, 0): roe = (net_income / equity) * 100

    fx = get_usd_krw() if currency == "USD" else None

    fig, ax = plt.subplots(figsize=(9, 7.5))
    top, left, right = (0.5, 0.92), (0.08, 0.12), (0.92, 0.12)
    xs = [left[0], right[0], top[0], left[0]]
    ys = [left[1], right[1], top[1], left[1]]
    ax.plot(xs, ys, color="#2c3e50", linewidth=2.2)
    ax.fill(xs, ys, alpha=0.06, color="#3498db")

    ax.annotate(f"시가총액\n{_human_dual(market_cap, currency, fx)}",
                xy=top, xytext=(0, 22), textcoords="offset points",
                ha="center", fontsize=12, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", fc="#fff3cd", ec="#856404"))
    ax.annotate(f"자본총계\n{_human_dual(equity, currency, fx)}",
                xy=left, xytext=(-12, -38), textcoords="offset points",
                ha="center", fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.4", fc="#d4edda", ec="#155724"))
    ax.annotate(f"당기순이익\n{_human_dual(net_income, currency, fx)}",
                xy=right, xytext=(12, -38), textcoords="offset points",
                ha="center", fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.4", fc="#f8d7da", ec="#721c24"))

    def mid(a, b): return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    mL = mid(top, left); mR = mid(top, right); mB = mid(left, right)
    ax.text(mL[0] - 0.05, mL[1], f"PBR\n{fmt_ratio(pbr)}",
            ha="right", va="center", fontsize=12, color="#1f4e79", fontweight="bold")
    ax.text(mR[0] + 0.05, mR[1], f"PER\n{fmt_ratio(per)}",
            ha="left", va="center", fontsize=12, color="#7d3c98", fontweight="bold")
    ax.text(mB[0], mB[1] - 0.06, f"ROE\n{fmt_ratio(roe, '%')}",
            ha="center", va="top", fontsize=12, color="#a04000", fontweight="bold")

    subtitle = title
    if currency == "USD" and fx:
        subtitle += f"  (환율 1 USD = {fx:,.2f} KRW)"
    ax.set_title(subtitle, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlim(-0.05, 1.05); ax.set_ylim(-0.05, 1.08)
    ax.set_aspect("equal"); ax.axis("off")
    plt.tight_layout()
    return fig

# ============================================================
# DB 조회
# ============================================================
def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

# ============================================================
# ============================================================
# UI
# ============================================================
# ============================================================
st.title("📊 한국/미국 상장사 투자지표 분석기")
st.caption("FinanceDataReader · OpenDartReader · yfinance — PER / PBR / ROE 자동 계산 + 이력 DB")

dart_key = get_dart_key()

with st.sidebar:
    st.header("⚙️ 설정")
    if not dart_key:
        st.warning("DART API 키가 없습니다. 한국 종목 재무가 비어있습니다.")
        manual_key = st.text_input("DART API 키 입력", type="password",
                                   help="https://opendart.fss.or.kr 에서 발급")
        if manual_key:
            dart_key = manual_key
    else:
        st.success("DART API 키 로드됨")
    st.markdown("---")
    st.markdown("**페이지**")
    page = st.radio("", ["🔍 종목 분석", "📐 삼각형 시뮬레이션", "🗄️ DB 조회"],
                    label_visibility="collapsed")

# ------------------------------------------------------------
# Page 1. 종목 분석
# ------------------------------------------------------------
if page == "🔍 종목 분석":
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("종목코드 / 티커 / 회사명 (일부 가능)", value="삼성전자",
                                placeholder="예) 005930, AAPL, 테슬라, 삼성")
    with col2:
        st.write(""); st.write("")
        do_search = st.button("🔎 검색", use_container_width=True)

    if keyword:
        candidates = search_stock(keyword, top_n=20)
        if candidates.empty:
            st.error("검색 결과가 없습니다.")
        else:
            # 표시용 라벨
            labels = candidates.apply(
                lambda r: f"[{r['country']}/{r['market']}] {r['name']} ({r['code']})", axis=1
            ).tolist()
            sel = st.selectbox("종목 선택", options=range(len(labels)),
                               format_func=lambda i: labels[i])
            picked = candidates.iloc[sel]

            if st.button("📥 데이터 가져오기 & 지표 계산", type="primary"):
                with st.spinner("데이터 수집 중..."):
                    row = analyze_stock(
                        code=picked["code"], dart_key=dart_key,
                        name=picked["name"], country=picked["country"],
                        market=picked["market"],
                    )
                st.session_state["last_row"] = row

            if "last_row" in st.session_state:
                r = st.session_state["last_row"]
                currency = r["currency"]
                fx = get_usd_krw() if currency == "USD" else None

                # KPI 카드
                st.subheader(f"{r['name']} ({r['code']}) — {r['snapshot_date']}")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("PER",        fmt_ratio(r["per"]))
                k2.metric("PBR",        fmt_ratio(r["pbr"]))
                k3.metric("ROE",        fmt_ratio(r["roe"], "%"))
                k4.metric("부채비율",   fmt_ratio(r["debt_ratio"], "%"))

                # 표
                view = pd.DataFrame({
                    "항목": [
                        "조회일", "통화", "종가", "시가총액",
                        "자본총계(순자산)", "당기순이익", "영업이익", "부채총계",
                        "부채비율(%)", "외국인비율(%)", "기관비율(%)",
                        "PER", "PBR", "ROE(%)",
                        "사업연도", "재무출처",
                    ],
                    "값": [
                        r["snapshot_date"], currency,
                        _human_dual(r["close_price"], currency, fx),
                        _human_dual(r["market_cap"], currency, fx),
                        _human_dual(r["equity"], currency, fx),
                        _human_dual(r["net_income"], currency, fx),
                        _human_dual(r["operating_income"], currency, fx),
                        _human_dual(r["total_liabilities"], currency, fx),
                        fmt_ratio(r["debt_ratio"]),
                        fmt_ratio(r["foreign_ratio"]),
                        fmt_ratio(r["institution_ratio"]),
                        fmt_ratio(r["per"]),
                        fmt_ratio(r["pbr"]),
                        fmt_ratio(r["roe"]),
                        r["bsns_year"] or "-",
                        r["source"] or "-",
                    ],
                })
                st.dataframe(view, hide_index=True, use_container_width=True)

                # 삼각형
                st.subheader("🔺 투자지표 삼각형")
                fig = draw_triangle(
                    market_cap=r["market_cap"], equity=r["equity"],
                    net_income=r["net_income"],
                    per=r["per"], pbr=r["pbr"], roe=r["roe"],
                    title=f"{r['name']} ({r['code']})", currency=currency,
                )
                st.pyplot(fig, use_container_width=False)

# ------------------------------------------------------------
# Page 2. 삼각형 시뮬레이션
# ------------------------------------------------------------
elif page == "📐 삼각형 시뮬레이션":
    st.subheader("수치를 직접 입력해서 삼각형 그리기")
    st.caption("가정·시나리오 분석용 — 음수도 가능")

    base_row = st.session_state.get("last_row", {})
    currency = st.radio("통화", ["KRW", "USD"],
                       index=0 if base_row.get("currency", "KRW") == "KRW" else 1,
                       horizontal=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        market_cap = st.number_input("시가총액", value=float(base_row.get("market_cap") or 0.0),
                                     format="%.2f", step=1e9)
    with c2:
        equity = st.number_input("자본총계", value=float(base_row.get("equity") or 0.0),
                                 format="%.2f", step=1e9)
    with c3:
        net_income = st.number_input("당기순이익", value=float(base_row.get("net_income") or 0.0),
                                     format="%.2f", step=1e9)

    title = st.text_input("타이틀", value=base_row.get("name", "시나리오 분석"))
    fig = draw_triangle(market_cap, equity, net_income, title=title, currency=currency)
    st.pyplot(fig, use_container_width=False)

# ------------------------------------------------------------
# Page 3. DB 조회
# ------------------------------------------------------------
elif page == "🗄️ DB 조회":
    tab1, tab2, tab3 = st.tabs(["기업 마스터", "이력 (전체)", "이력 (종목별)"])
    with tab1:
        df = query("SELECT * FROM companies ORDER BY updated_at DESC")
        st.dataframe(df, use_container_width=True)
    with tab2:
        df = query("""
            SELECT snapshot_date, code, name, currency, per, pbr, roe, debt_ratio
              FROM metrics_history
             ORDER BY snapshot_date DESC, code
        """)
        st.dataframe(df, use_container_width=True)
    with tab3:
        code = st.text_input("종목코드 / 티커", value="005930")
        if code:
            df = query("""
                SELECT snapshot_date, name, close_price, market_cap, equity, net_income,
                       per, pbr, roe, debt_ratio
                  FROM metrics_history
                 WHERE code = ?
                 ORDER BY snapshot_date DESC
            """, (code,))
            st.dataframe(df, use_container_width=True)
