# 🚀 통합 크롤러 대시보드 & 매니저 (Unified Crawler Dashboard & Manager)

개별적으로 흩어져 관리되던 크롤러 리포지토리(**EtoLand, AVDBS, ZDNet**)를 단일 파이썬 코드베이스로 깔끔하게 통합하고, 새롭게 **GeekNews** 및 **나만의 크롤러 제작기(Universal Creator)**를 탑재한 세련된 다크 글래스모피즘 웹 대시보드 및 CLI 구동 프로그램입니다.

---

## ✨ 주요 기능

1. **4대 채널 기본 크롤러 내장**:
   - **EtoLand (에토랜드)**: 약후 Humor 게시판의 새 글과 본문 내 이미지/비디오를 파싱 및 다운로드하여 전송합니다.
   - **AVDBS T50 & T22**: Playwright 브라우저 로그인을 통해 고해상도 미디어를 파싱합니다.
   - **ZDNet News**: 일본 ZDNet 소프트웨어 기사(한글 자동 번역) 및 한국 ZDNet 인공지능 뉴스를 수집합니다.
   - **GeekNews (긱뉴스)**: IT, AI, 오픈소스 등 기술 트렌드 뉴스(Hada.io)의 요약과 원문/토론 링크를 수집합니다.
2. **나만의 크롤러 제작기 (Universal Creator)**:
   - 새로운 크롤러를 코딩 없이 웹 대시보드 상에서 즉석 생성할 수 있습니다.
   - 대상 URL과 게시글 박스, 제목, 링크, 본문의 CSS 선택자를 지정하여 **파싱 미리보기 테스트**를 거친 뒤, 저장 버튼을 누르면 대시보드에 즉시 연동 카드와 스케줄이 등록됩니다.
3. **백그라운드 자동 스케줄러**:
   - 대시보드 우측 하단 스위치를 켜면 설정한 주기(10분, 30분, 1시간, 2시간, 6시간, 12시간 등)마다 백그라운드에서 크롤러가 자동 동작하며 새 소식을 전송합니다.
4. **실시간 로그 모니터링**:
   - `data/crawler.log` 파일의 최신 출력을 웹 화면 콘솔에 실시간 출력하여 장애 여부나 작업 진행 상황을 브라우저에서 편리하게 모니터링합니다.
5. **환경변수(.env) 웹 에디터**:
   - 텔레그램 봇 토큰(`TELEGRAM_TOKEN`), 채팅방 ID(`TELEGRAM_CHAT_ID`), AVDBS 로그인 정보 등을 대시보드에서 수정하고 로컬 `.env` 파일에 즉시 영구 보관할 수 있습니다.
6. **자동 데이터 마이그레이션**:
   - 구동 시 기존에 각 하위 폴더에 들어있던 크롤링 중복 이력 파일(`seen_ids.txt`, `sent_posts.json`, `sent_articles.json`)과 각각의 `.env` 파일 설정값을 감지하여 `data/` 및 루트 `.env`로 안전하게 병합 이관합니다.

---

## 📂 프로젝트 구조

```text
├── crawlers/
│   ├── __init__.py
│   ├── base.py          # 공통 텔레그램 전송, 로깅 핸들러 및 seen DB 기능 정의
│   ├── etoland.py       # 에토랜드 크롤러 클래스
│   ├── avdbs.py         # Playwright 기반 AVDBS 로그인/크롤러 클래스
│   ├── zdnet.py         # ZDNet 기사 크롤러 및 번역 클래스
│   ├── geeknews.py      # GeekNews 크롤러 클래스
│   └── generic.py       # Universal Creator를 구동하는 범용 CSS 선택자 기반 크롤러
├── server/
│   ├── __init__.py
│   ├── app.py           # FastAPI 백엔드 (API 엔드포인트 및 백그라운드 스케줄러 루프)
│   └── templates/
│       └── index.html   # 글래스모피즘 기반 다크 테마 웹 대시보드 UI
├── data/                # 크롤링 이력 JSON 및 crawler.log가 보관되는 데이터 폴더
├── .env                 # 환경변수 설정 파일 (자동 생성 및 웹 수정)
├── .gitignore           # 민감 정보 및 임시 파일 업로드 방지 설정
├── requirements.txt     # 통합 패키지 요구사항 의존성 명세
├── run.py               # 프로그램 통합 진입점 (마이그레이션, --server, --run 지원)
└── README.md            # 본 프로젝트 설명 문서
```

---

## ⚙️ 시작하기 (Installation & Setup)

### 1. 필수 의존성 설치
로컬 파이썬(Python 3.8 이상 추천) 환경에서 아래 명령어를 실행하여 필요 라이브러리를 설치합니다:
```bash
pip install -r requirements.txt
```

### 2. Playwright 브라우저 바이너리 설치 (AVDBS 크롤러 필수)
AVDBS 크롤러 구동을 위해 headless 브라우저를 설치해 주어야 합니다:
```bash
playwright install chromium
```

### 3. 웹 대시보드 기동
통합 웹 대시보드 서버를 시작합니다:
```bash
python run.py --server
```
기본적으로 **`http://localhost:8000`** 주소로 웹 서버가 실행됩니다. 브라우저로 접속해 사용해 주세요.

### 4. CLI 모드로 특정 크롤러 즉시 단독 실행
대시보드 없이 터미널에서 스케줄러 등으로 단독 실행 시 활용 가능합니다:
```bash
# GeekNews 즉시 단독 실행
python run.py --run geeknews

# 내장된 4대 크롤러 순차 실행
python run.py --run all
```

---

## 🔒 라이선스 및 주의사항
* 본 프로그램은 로컬 호스트(`127.0.0.1`) 환경에서 전적으로 동작하며, 개인적 정보 수집 및 텔레그램 발송 목적으로만 사용하도록 설계되었습니다.
* 타겟 웹사이트의 서비스 이용약관을 준수하여 과도한 요청(Dos 수준)이 가지 않도록 스케줄러 실행 주기를 적절히(최소 10분 이상) 조율해 주시기 바랍니다.
