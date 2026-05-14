# 📊 한국/미국 상장사 투자지표 분석기

FinanceDataReader + OpenDartReader + yfinance 로 PER / PBR / ROE 를 자동 계산하고,
SQLite 에 날짜별·기업별 이력을 누적 저장하는 Streamlit 웹앱.

## ✨ 기능

- 종목코드 / 티커 / 회사명 일부로 검색 (한국 KRX + 미국 NASDAQ/NYSE)
- 시가총액, 종가, 자본총계, 당기순이익, 영업이익, 부채총계 자동 수집
- PER / PBR / ROE / 부채비율 자동 계산
- **삼각형 다이어그램**: 시총-자본-순이익 꼭지점, PER/PBR/ROE 변
- 수치를 직접 입력해 **시나리오 시뮬레이션** 가능
- 미국 종목은 **USD + 오늘 환율 기준 KRW 병기**
- 모든 조회 결과는 SQLite DB에 누적

## 🗂️ 구조

```
.
├── app.py                      # Streamlit 메인
├── requirements.txt            # Python 의존성
├── packages.txt                # 시스템 패키지 (한글 폰트)
├── .streamlit/
│   ├── config.toml             # 테마
│   └── secrets.toml.example    # API 키 템플릿 (실제 키는 클라우드 Secrets에)
├── .gitignore
└── README.md
```

## 🚀 로컬 실행

```bash
git clone https://github.com/<your-id>/<repo>.git
cd <repo>
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

export DART_API_KEY="여기에40자리키"  # Windows: set DART_API_KEY=...
streamlit run app.py
```

`http://localhost:8501` 접속.

## ☁️ Streamlit Community Cloud 배포 (무료)

### 1) GitHub에 푸시

```bash
git init
git add .
git commit -m "init: investment metrics app"
git branch -M main
git remote add origin https://github.com/<your-id>/<repo>.git
git push -u origin main
```

### 2) Streamlit Cloud 연결

1. https://share.streamlit.io 접속 → GitHub 로그인
2. **Create app** → Repository, Branch(`main`), Main file path(`app.py`) 지정
3. **Deploy** 클릭
4. 빌드가 끝나면 `https://<your-id>-<repo>.streamlit.app` URL 발급

### 3) DART API 키 등록 (Secrets)

배포된 앱의 우상단 메뉴 → **Settings → Secrets** → 아래 입력 후 Save:

```toml
DART_API_KEY = "여기에40자리DART인증키"
```

저장하면 앱이 자동 재시작되며 한국 종목 재무 데이터가 정상 조회됩니다.

> Secrets는 GitHub에 노출되지 않습니다. 절대 `secrets.toml` 실파일을 커밋하지 마세요 (`.gitignore`로 이미 제외됨).

## 🔑 DART API 키 발급

1. https://opendart.fss.or.kr → 회원가입
2. 인증키 신청/관리 → 인증키 신청
3. 즉시 발급되는 40자리 키 복사

무료, 일 20,000 호출 한도.

## ⚠️ 주의 사항

- **데이터베이스 영속성**: Streamlit Community Cloud 인스턴스는 재시작 시 파일이 휘발됩니다. 누적 분석이 필요하면 외부 DB(Supabase, PlanetScale, Turso 등)로 교체하세요. (`app.py`의 `DB_PATH` 부분 수정)
- **무료 플랜 슬립**: 며칠 미사용 시 슬립 모드로 들어가며 첫 접속 시 깨우는 데 ~30초 걸립니다.
- **외국인/기관 비율**: 한국은 별도 소스(KRX 정보데이터, pykrx)가 필요해 현재 `None` 반환. 미국은 yfinance에서 institutional 비율만 제공.
- **DART 계정명 매칭**: 회사별로 계정명 표기가 다를 수 있어 일부 종목은 값이 비어있을 수 있습니다. `ACCOUNT_PATTERNS` 리스트에 패턴 추가로 보강 가능.

## 📜 라이선스

MIT
