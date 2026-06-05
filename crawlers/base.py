import os
import json
import logging
import requests
from pathlib import Path
from io import BytesIO

# 공통 데이터 폴더 및 로그 설정
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = DATA_DIR / "crawler.log"

# 표준 로깅 설정
logger_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=logger_format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

class BaseCrawler:
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self.seen_file = DATA_DIR / f"{name}_seen.json"
        self.seen_data = self._load_seen()

    def _load_seen(self) -> dict:
        """이전 크롤링 완료 목록(seen)을 로드합니다."""
        if not self.seen_file.exists():
            return {}
        try:
            with open(self.seen_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # 형식을 {"title": ..., "time": ...} 형태로 표준화
                    normalized = {}
                    for k, v in data.items():
                        if isinstance(v, dict):
                            normalized[k] = v
                        else:
                            normalized[k] = {"title": v, "time": ""}
                    return normalized
                elif isinstance(data, list):
                    # 구버전 리스트 형태 마이그레이션
                    return {item: {"title": "", "time": ""} for item in data}
                return {}
        except Exception as e:
            self.logger.warning(f"읽음 상태 파일 로드 실패 ({self.name}): {e}")
            return {}

    def save_seen(self):
        """크롤링 완료 목록을 저장합니다."""
        try:
            with open(self.seen_file, "w", encoding="utf-8") as f:
                json.dump(self.seen_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"읽음 상태 파일 저장 실패 ({self.name}): {e}")

    def is_seen(self, key: str) -> bool:
        """이미 크롤링된 항목인지 확인합니다."""
        return key in self.seen_data

    def mark_seen(self, key: str, value: str = ""):
        """크롤링 완료 표시를 합니다."""
        now_str = logging.Formatter().formatTime(logging.LogRecord("", 0, "", 0, "", (), None))
        self.seen_data[key] = {
            "title": value,
            "time": now_str
        }
        self.save_seen()

    def send_telegram_text(self, token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
        """텔레그램으로 텍스트 메시지를 전송합니다."""
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                self.logger.info("텔레그램 텍스트 메시지 전송 성공")
                return True
            else:
                self.logger.error(f"텔레그램 텍스트 메시지 전송 실패: {r.status_code} {r.text}")
        except Exception as e:
            self.logger.error(f"텔레그램 요청 중 예외 발생: {e}")
        return False

    def send_telegram_media(self, token: str, chat_id: str, media_type: str, media_url: str, caption: str = None, referer: str = None, download_and_upload: bool = True) -> bool:
        """텔레그램으로 이미지 또는 동영상을 전송합니다."""
        method = "sendPhoto" if media_type == "photo" else "sendVideo"
        url = f"https://api.telegram.org/bot{token}/{method}"
        
        headers = {}
        if referer:
            headers["Referer"] = referer
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

        if download_and_upload:
            try:
                self.logger.info(f"미디어 다운로드 후 업로드 중: {media_url}")
                r_dl = requests.get(media_url, headers=headers, timeout=20)
                if r_dl.status_code == 200 and r_dl.content:
                    file_name = "image.jpg" if media_type == "photo" else "video.mp4"
                    files = {media_type: (file_name, BytesIO(r_dl.content))}
                    payload = {"chat_id": chat_id, "caption": caption or "", "parse_mode": "HTML"}
                    r = requests.post(url, data=payload, files=files, timeout=60)
                    if r.status_code == 200:
                        self.logger.info(f"텔레그램 {media_type} 전송 성공 (다운로드 후 업로드)")
                        return True
                    else:
                        self.logger.error(f"텔레그램 {media_type} 전송 실패 (업로드 오류): {r.status_code} {r.text}")
            except Exception as e:
                self.logger.error(f"텔레그램 전송용 미디어 다운로드 실패 ({media_url}): {e}")
        
        # 다운로드 업로드가 실패하거나 꺼져 있을 경우 URL 전송 시도
        self.logger.info(f"미디어 URL로 직접 전송 중: {media_url}")
        payload = {
            "chat_id": chat_id,
            media_type: media_url,
            "caption": caption or "",
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                self.logger.info(f"텔레그램 {media_type} 전송 성공 (URL)")
                return True
            else:
                self.logger.error(f"텔레그램 {media_type} 전송 실패 (URL): {r.status_code} {r.text}")
        except Exception as e:
            self.logger.error(f"텔레그램 {media_type} URL 전송 예외 발생: {e}")
        return False
