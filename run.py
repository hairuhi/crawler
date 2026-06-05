import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv, set_key

# --- 마이그레이션 로직 ---
def migrate_existing_data():
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print("[migration] 기존 데이터 파일 마이그레이션 검사 중...")

    # 1. 에토랜드 이력 마이그레이션
    old_etoland = Path("etoland-crawler-telegram/state/seen_ids.txt")
    new_etoland = data_dir / "etoland_seen.json"
    if old_etoland.exists() and not new_etoland.exists():
        try:
            with open(old_etoland, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            seen_dict = {line.strip(): {"title": "", "time": ""} for line in lines if line.strip()}
            with open(new_etoland, "w", encoding="utf-8") as f:
                json.dump(seen_dict, f, ensure_ascii=False, indent=2)
            print(f"[migration] 에토랜드 크롤링 이력 마이그레이션 성공 ({len(seen_dict)}개)")
        except Exception as e:
            print(f"[migration] 에토랜드 마이그레이션 실패: {e}")

    # 2. AVDBS 이력 마이그레이션
    old_avdbs = Path("avdbs-t50/sent_posts.json")
    new_avdbs = data_dir / "avdbs_seen.json"
    if old_avdbs.exists() and not new_avdbs.exists():
        try:
            with open(old_avdbs, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                seen_dict = {url: {"title": "", "time": ""} for url in data}
            else:
                seen_dict = {}
            with open(new_avdbs, "w", encoding="utf-8") as f:
                json.dump(seen_dict, f, ensure_ascii=False, indent=2)
            print(f"[migration] AVDBS 크롤링 이력 마이그레이션 성공 ({len(seen_dict)}개)")
        except Exception as e:
            print(f"[migration] AVDBS 마이그레이션 실패: {e}")

    # 3. ZDNet 이력 마이그레이션
    old_zdnet = Path("ZDNET_JAPAN/sent_articles.json")
    new_zdnet = data_dir / "zdnet_seen.json"
    if old_zdnet.exists() and not new_zdnet.exists():
        try:
            with open(old_zdnet, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                seen_dict = {k: {"title": "", "time": v} for k, v in data.items()}
            else:
                seen_dict = {}
            with open(new_zdnet, "w", encoding="utf-8") as f:
                json.dump(seen_dict, f, ensure_ascii=False, indent=2)
            print(f"[migration] ZDNet 크롤링 이력 마이그레이션 성공 ({len(seen_dict)}개)")
        except Exception as e:
            print(f"[migration] ZDNet 마이그레이션 실패: {e}")

    # 4. 개별 .env 파일 마이그레이션
    root_env = Path(".env")
    if not root_env.exists():
        root_env.touch()
        
    env_keys = {}
    load_dotenv(dotenv_path=root_env, override=True)
    
    target_keys = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "AVDBS_ID", "AVDBS_PW", "JAPAN_SOFTWARE_URL", "KOREA_AI_URL"]
    for k in target_keys:
        val = os.getenv(k)
        if val:
            env_keys[k] = val

    def read_env_keys(env_path):
        keys = {}
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        keys[k.strip()] = v.strip().strip("'").strip('"')
            except Exception as e:
                print(f"[migration] 하위 .env ({env_path}) 읽기 실패: {e}")
        return keys

    # 하위 폴더 env들 병합
    sub_keys = {}
    sub_keys.update(read_env_keys(Path("ZDNET_JAPAN/.env")))
    sub_keys.update(read_env_keys(Path("avdbs-t50/.env")))
    sub_keys.update(read_env_keys(Path("etoland-crawler-telegram/.env")))
    
    # 동의어 매핑
    synonyms = {
        "TELEGRAM_BOT_TOKEN": "TELEGRAM_TOKEN",
    }
    
    for k, v in sub_keys.items():
        mapped_key = synonyms.get(k, k)
        if mapped_key in target_keys:
            if mapped_key not in env_keys:
                env_keys[mapped_key] = v
                set_key(str(root_env), mapped_key, v)
                print(f"[migration] 설정 값 마이그레이션 적용: {mapped_key}")

# --- CLI 모드 개별 크롤러 실행기 ---
def run_cli_crawler(crawler_name):
    # .env 적용
    load_dotenv(dotenv_path=Path(".env"), override=True)
    
    if crawler_name == "etoland":
        from crawlers.etoland import EtolandCrawler
        crawler = EtolandCrawler()
        crawler.run()
    elif crawler_name == "avdbs":
        from crawlers.avdbs import AvdbsCrawler
        crawler = AvdbsCrawler()
        crawler.run()
    elif crawler_name == "zdnet":
        from crawlers.zdnet import ZdnetCrawler
        crawler = ZdnetCrawler()
        crawler.run()
    elif crawler_name == "geeknews":
        from crawlers.geeknews import GeeknewsCrawler
        crawler = GeeknewsCrawler()
        crawler.run()
    elif crawler_name == "all":
        print("[cli] 전체 크롤러 순차 실행 중...")
        from crawlers.etoland import EtolandCrawler
        from crawlers.avdbs import AvdbsCrawler
        from crawlers.zdnet import ZdnetCrawler
        from crawlers.geeknews import GeeknewsCrawler
        
        print("[cli] 1/4 에토랜드 실행 중...")
        try: EtolandCrawler().run()
        except Exception as e: print(f"에토랜드 오류: {e}")
        
        print("[cli] 2/4 AVDBS 실행 중...")
        try: AvdbsCrawler().run()
        except Exception as e: print(f"AVDBS 오류: {e}")
        
        print("[cli] 3/4 ZDNet 실행 중...")
        try: ZdnetCrawler().run()
        except Exception as e: print(f"ZDNet 오류: {e}")

        print("[cli] 4/4 GeekNews 실행 중...")
        try: GeeknewsCrawler().run()
        except Exception as e: print(f"GeekNews 오류: {e}")
    else:
        print(f"[error] 알 수 없는 크롤러 이름: {crawler_name}", file=sys.stderr)
        sys.exit(1)

# --- 메인 시작점 ---
def main():
    parser = argparse.ArgumentParser(description="통합 크롤러 매니저 실행 스크립트")
    parser.add_argument("--server", action="store_true", help="웹 대시보드 서버를 시작합니다.")
    parser.add_argument("--run", type=str, choices=["etoland", "avdbs", "zdnet", "geeknews", "all"], help="CLI 상에서 특정 크롤러를 즉시 단독 실행합니다.")
    parser.add_argument("--port", type=int, default=8000, help="웹 서버 실행 시 바인딩할 포트 번호 (기본값: 8000)")
    
    args = parser.parse_args()

    # 1. 자동 마이그레이션 수행
    migrate_existing_data()

    # 2. 파라미터 처리
    if args.run:
        run_cli_crawler(args.run)
    elif args.server or not len(sys.argv) > 1:
        # uvicorn 실행
        import uvicorn
        print(f"[server] 웹 대시보드를 시작합니다. 브라우저에서 http://localhost:{args.port} 주소로 접속해 주세요.")
        uvicorn.run("server.app:app", host="127.0.0.1", port=args.port, reload=False)

if __name__ == "__main__":
    main()
