import os
import json
import logging
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv, set_key

from crawlers.etoland import EtolandCrawler
from crawlers.avdbs import AvdbsCrawler
from crawlers.zdnet import ZdnetCrawler
from crawlers.geeknews import GeeknewsCrawler

# 커스텀 크롤러 데이터 저장 경로
CUSTOM_CRAWLERS_FILE = Path("data/custom_crawlers.json")

def load_custom_crawlers() -> dict:
    if not CUSTOM_CRAWLERS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_CRAWLERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_custom_crawlers(data: dict):
    with open(CUSTOM_CRAWLERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sync_crawler_states():
    customs = load_custom_crawlers()
    for name in customs.keys():
        if name not in RUNNING_LOCKS:
            RUNNING_LOCKS[name] = False
        if name not in LAST_RUN_INFO:
            LAST_RUN_INFO[name] = {"time": "N/A", "status": "대기 중", "count": 0}

# 환경변수 파일 위치 설정
ENV_PATH = Path(".env")
if not ENV_PATH.exists():
    ENV_PATH.touch()

load_dotenv(dotenv_path=ENV_PATH)

# FastAPI 인스턴스 생성
app = FastAPI(title="Unified Crawler Manager Dashboard")

# 실행 락(Lock) 및 상태 관리 변수
RUNNING_LOCKS = {
    "etoland": False,
    "avdbs": False,
    "zdnet": False,
    "geeknews": False,
    "playwright": False
}

LAST_RUN_INFO = {
    "etoland": {"time": "N/A", "status": "대기 중", "count": 0},
    "avdbs": {"time": "N/A", "status": "대기 중", "count": 0},
    "zdnet": {"time": "N/A", "status": "대기 중", "count": 0},
    "geeknews": {"time": "N/A", "status": "대기 중", "count": 0},
    "playwright": {"time": "N/A", "status": "대기 중"}
}

# 서버 자체 로거 정의
logger = logging.getLogger("server")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

class ConfigModel(BaseModel):
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    AVDBS_ID: str = ""
    AVDBS_PW: str = ""
    JAPAN_SOFTWARE_URL: str = ""
    KOREA_AI_URL: str = ""
    SCHEDULER_ENABLED: str = "0"
    SCHEDULER_INTERVAL_MINUTES: str = "30"

# --- 비동기 크롤러 실행기 ---
async def run_crawler_async(name: str):
    # 상태 딕셔너리 동기화 보장
    if name not in RUNNING_LOCKS:
        RUNNING_LOCKS[name] = False
    if name not in LAST_RUN_INFO:
        LAST_RUN_INFO[name] = {"time": "N/A", "status": "대기 중", "count": 0}

    if RUNNING_LOCKS.get(name):
        logger.warning(f"이미 {name} 크롤러가 작동 중입니다. 실행 요청을 무시합니다.")
        return
    
    RUNNING_LOCKS[name] = True
    LAST_RUN_INFO[name]["status"] = "실행 중"
    LAST_RUN_INFO[name]["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        logger.info(f"[{name.upper()}] 크롤러 실행을 시작합니다.")
        if name == "etoland":
            crawler = EtolandCrawler()
            count = await asyncio.to_thread(crawler.run)
        elif name == "avdbs":
            crawler = AvdbsCrawler()
            count = await asyncio.to_thread(crawler.run)
        elif name == "zdnet":
            crawler = ZdnetCrawler()
            count = await asyncio.to_thread(crawler.run)
        elif name == "geeknews":
            crawler = GeeknewsCrawler()
            count = await asyncio.to_thread(crawler.run)
        else:
            customs = load_custom_crawlers()
            if name in customs:
                from crawlers.generic import GenericCrawler
                crawler = GenericCrawler(customs[name])
                count = await asyncio.to_thread(crawler.run)
            else:
                raise ValueError("알 수 없는 크롤러 이름")
            
        LAST_RUN_INFO[name]["status"] = "성공"
        LAST_RUN_INFO[name]["count"] = count
        logger.info(f"[{name.upper()}] 크롤러 성공적으로 완료. 전송 건수: {count}")
    except Exception as e:
        LAST_RUN_INFO[name]["status"] = "실패"
        logger.error(f"[{name.upper()}] 크롤러 실행 오류: {e}")
    finally:
        RUNNING_LOCKS[name] = False

# --- Playwright Chromium 브라우저 설치 실행기 ---
async def playwright_install_async():
    if RUNNING_LOCKS["playwright"]:
        return
    
    RUNNING_LOCKS["playwright"] = True
    LAST_RUN_INFO["playwright"]["status"] = "진행 중"
    LAST_RUN_INFO["playwright"]["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        logger.info("Playwright Chromium 다운로드를 시작합니다...")
        def install_cmd():
            res = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True, check=True)
            return res.stdout
        stdout = await asyncio.to_thread(install_cmd)
        logger.info(f"Playwright Chromium 설치 완료:\n{stdout}")
        LAST_RUN_INFO["playwright"]["status"] = "성공"
    except Exception as e:
        logger.error(f"Playwright Chromium 설치 오류: {e}")
        LAST_RUN_INFO["playwright"]["status"] = "실패"
    finally:
        RUNNING_LOCKS["playwright"] = False

# --- 백그라운드 스케줄러 루프 ---
async def scheduler_loop():
    # 켜지자마자 바로 실행될 수 있도록 큰 값으로 초기화
    elapsed_minutes = 99999
    while True:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        enabled = os.getenv("SCHEDULER_ENABLED", "0").strip() == "1"
        try:
            interval_mins = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "30").strip())
        except ValueError:
            interval_mins = 30
        
        if enabled:
            if elapsed_minutes >= interval_mins:
                logger.info(f"[스케줄러] 자동 크롤러 주기 실행 도달 ({interval_mins}분). 모든 크롤러 가동을 시작합니다.")
                
                # 빌트인 목록 + 커스텀 목록 동적 결합
                names = ["etoland", "avdbs", "zdnet", "geeknews"]
                customs = load_custom_crawlers()
                names.extend(customs.keys())
                
                for name in names:
                    if name not in RUNNING_LOCKS:
                        RUNNING_LOCKS[name] = False
                    if not RUNNING_LOCKS[name]:
                        asyncio.create_task(run_crawler_async(name))
                elapsed_minutes = 0
            else:
                elapsed_minutes += 1
        else:
            # 꺼진 경우 다음 켤 때 즉시 수행되도록 초기화
            elapsed_minutes = 99999
            
        await asyncio.sleep(60)

# --- FastAPI 이벤트 리스너 ---
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scheduler_loop())

# --- REST API 엔드포인트 ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html 파일을 찾을 수 없습니다. 경로를 확인해 주세요.")
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/status")
def get_status():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    sync_crawler_states()
    return {
        "crawlers": LAST_RUN_INFO,
        "running_locks": RUNNING_LOCKS,
        "custom_crawlers": load_custom_crawlers(),
        "scheduler": {
            "enabled": os.getenv("SCHEDULER_ENABLED", "0").strip() == "1",
            "interval_minutes": int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "30").strip())
        }
    }

@app.post("/api/run/{name}")
def trigger_crawler(name: str, background_tasks: BackgroundTasks):
    sync_crawler_states()
    built_ins = ["etoland", "avdbs", "zdnet", "geeknews"]
    customs = list(load_custom_crawlers().keys())
    
    if name not in built_ins + customs + ["all"]:
        raise HTTPException(status_code=400, detail="유효하지 않은 크롤러 명칭입니다.")
        
    if name == "all":
        for crawler_name in built_ins + customs:
            if not RUNNING_LOCKS.get(crawler_name, False):
                background_tasks.add_task(run_crawler_async, crawler_name)
        return {"status": "triggered", "target": "all"}
    
    if RUNNING_LOCKS.get(name, False):
        return {"status": "already_running", "target": name}
        
    background_tasks.add_task(run_crawler_async, name)
    return {"status": "triggered", "target": name}

@app.post("/api/playwright-install")
def trigger_playwright_install(background_tasks: BackgroundTasks):
    if RUNNING_LOCKS["playwright"]:
        return {"status": "already_running"}
    background_tasks.add_task(playwright_install_async)
    return {"status": "triggered"}

@app.get("/api/logs")
def get_logs():
    log_file = Path("data/crawler.log")
    if not log_file.exists():
        return PlainTextResponse("아직 로그 데이터가 쌓이지 않았습니다.")
        
    try:
        # 최근 200줄의 로그만 반환
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            last_lines = lines[-200:]
            return PlainTextResponse("".join(last_lines))
    except Exception as e:
        return PlainTextResponse(f"로그 파일 읽기 오류: {e}")

@app.get("/api/config")
def get_config():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    return {
        "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
        "AVDBS_ID": os.getenv("AVDBS_ID", ""),
        "AVDBS_PW": os.getenv("AVDBS_PW", ""),
        "JAPAN_SOFTWARE_URL": os.getenv("JAPAN_SOFTWARE_URL", "https://japan.zdnet.com/software/"),
        "KOREA_AI_URL": os.getenv("KOREA_AI_URL", "https://zdnet.co.kr/newskey/?lstcode=%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5"),
        "SCHEDULER_ENABLED": os.getenv("SCHEDULER_ENABLED", "0"),
        "SCHEDULER_INTERVAL_MINUTES": os.getenv("SCHEDULER_INTERVAL_MINUTES", "30")
    }

@app.post("/api/config")
def save_config(config: ConfigModel):
    try:
        # dotenv 파일에 저장
        set_key(str(ENV_PATH), "TELEGRAM_TOKEN", config.TELEGRAM_TOKEN)
        set_key(str(ENV_PATH), "TELEGRAM_CHAT_ID", config.TELEGRAM_CHAT_ID)
        set_key(str(ENV_PATH), "AVDBS_ID", config.AVDBS_ID)
        set_key(str(ENV_PATH), "AVDBS_PW", config.AVDBS_PW)
        set_key(str(ENV_PATH), "JAPAN_SOFTWARE_URL", config.JAPAN_SOFTWARE_URL)
        set_key(str(ENV_PATH), "KOREA_AI_URL", config.KOREA_AI_URL)
        set_key(str(ENV_PATH), "SCHEDULER_ENABLED", config.SCHEDULER_ENABLED)
        set_key(str(ENV_PATH), "SCHEDULER_INTERVAL_MINUTES", config.SCHEDULER_INTERVAL_MINUTES)
        
        # 임시 환경 변수 재정리
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        logger.info("환경 설정값이 업데이트되었습니다.")
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 저장 오류: {e}")

# --- 커스텀 크롤러 생성용 Pydantic 모델 ---
class CustomCrawlerModel(BaseModel):
    name: str
    url: str
    item_selector: str
    title_selector: str = ""
    link_selector: str = ""
    desc_selector: str = ""

class TestCrawlerModel(BaseModel):
    url: str
    item_selector: str
    title_selector: str = ""
    link_selector: str = ""
    desc_selector: str = ""

@app.post("/api/custom-crawlers")
def add_custom_crawler(config: CustomCrawlerModel):
    # 영문/숫자 매칭 등으로 크롤러 이름 클렌징
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "", config.name)
    if not clean_name:
        raise HTTPException(status_code=400, detail="크롤러 이름은 영문, 숫자, 언더바(_)만 포함해야 합니다.")
        
    customs = load_custom_crawlers()
    custom_config = config.dict()
    custom_config["name"] = clean_name # 클렌징 이름 적용
    customs[clean_name] = custom_config
    save_custom_crawlers(customs)
    sync_crawler_states()
    return {"status": "created", "name": clean_name}

@app.delete("/api/custom-crawlers/{name}")
def delete_custom_crawler(name: str):
    customs = load_custom_crawlers()
    if name in customs:
        del customs[name]
        save_custom_crawlers(customs)
        
        # 락 및 정보 해제
        if name in RUNNING_LOCKS: del RUNNING_LOCKS[name]
        if name in LAST_RUN_INFO: del LAST_RUN_INFO[name]
        
        # 이력 파일도 존재하면 삭제 처리 (옵션)
        seen_file = Path(f"data/generic_{name}_seen.json")
        if seen_file.exists():
            try: seen_file.unlink()
            except Exception: pass
            
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="해당 크롤러를 찾을 수 없습니다.")

@app.post("/api/custom-crawlers/test")
async def test_custom_crawler(config: TestCrawlerModel):
    try:
        from crawlers.generic import GenericCrawler
        tmp_config = {
            "name": "test_preview",
            "url": config.url,
            "item_selector": config.item_selector,
            "title_selector": config.title_selector,
            "link_selector": config.link_selector,
            "desc_selector": config.desc_selector
        }
        crawler = GenericCrawler(tmp_config)
        items = await asyncio.to_thread(crawler.fetch_items)
        return {"status": "ok", "items": items[:15]}  # 상위 15개 미리보기 반환
    except Exception as e:
        logger.error(f"파싱 테스트 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import re

@app.get("/api/history")
def get_history():
    history = []
    
    # 1. 에토랜드 이력
    etoland_file = Path("data/etoland_seen.json")
    if etoland_file.exists():
        try:
            with open(etoland_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    # k = etoland:bo_table:wr_id
                    parts = k.split(":")
                    title = f"에토랜드 게시글 wr_id={parts[-1]}" if len(parts) >= 3 else k
                    history.append({
                        "crawler": "EtoLand",
                        "title": v.get("title") or title,
                        "key": k,
                        "time": v.get("time") or "N/A"
                    })
        except Exception:
            pass

    # 2. AVDBS 이력
    avdbs_file = Path("data/avdbs_seen.json")
    if avdbs_file.exists():
        try:
            with open(avdbs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    history.append({
                        "crawler": "AVDBS",
                        "title": v.get("title") or k,
                        "key": k,
                        "time": v.get("time") or "N/A"
                    })
        except Exception:
            pass

    # 3. ZDNet 이력
    zdnet_file = Path("data/zdnet_seen.json")
    if zdnet_file.exists():
        try:
            with open(zdnet_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    history.append({
                        "crawler": "ZDNet",
                        "title": v.get("title") or k,
                        "key": k,
                        "time": v.get("time") or "N/A"
                    })
        except Exception:
            pass

    # 4. GeekNews 이력
    geeknews_file = Path("data/geeknews_seen.json")
    if geeknews_file.exists():
        try:
            with open(geeknews_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    history.append({
                        "crawler": "GeekNews",
                        "title": v.get("title") or k,
                        "key": k,
                        "time": v.get("time") or "N/A"
                    })
        except Exception:
            pass

    # 5. 커스텀 크롤러 이력 수집
    for p in Path("data").glob("generic_*_seen.json"):
        name = p.name.replace("generic_", "").replace("_seen.json", "")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    history.append({
                        "crawler": f"Custom ({name})",
                        "title": v.get("title") or k,
                        "key": k,
                        "time": v.get("time") or "N/A"
                    })
        except Exception:
            pass

    # 최근 순 정렬 (시간 정보 기준 내림차순, 비어있으면 뒤로 보냄)
    def get_time_key(x):
        t = x.get("time")
        if not t or t == "N/A":
            return "0000-00-00 00:00:00"
        return t

    history.sort(key=get_time_key, reverse=True)
    return history[:100]  # 최근 100개만 UI로 송출
