import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from googletrans import Translator
from crawlers.base import BaseCrawler

class ZdnetCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("zdnet")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ZDNetCrawler/2.0; +https://github.com/hairuhi)"
        }
        self.japan_software_url = os.getenv("JAPAN_SOFTWARE_URL", "https://japan.zdnet.com/software/")
        self.korea_ai_url = os.getenv("KOREA_AI_URL", "https://zdnet.co.kr/newskey/?lstcode=%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5")
        try:
            self.translator = Translator()
        except Exception as e:
            self.logger.error(f"구글 번역기 초기화 중 에러 발생: {e}")
            self.translator = None

    def fetch_html(self, url: str) -> str:
        resp = requests.get(url, headers=self.headers, timeout=20)
        resp.raise_for_status()
        return resp.text

    def is_within_last_24h(self, dt: datetime) -> bool:
        if dt is None:
            return False
        # 기사 시간(KST/JST = UTC+9) 기준으로 연산 수행
        now_local = datetime.utcnow() + timedelta(hours=9)
        cutoff = now_local - timedelta(hours=24)
        return cutoff <= dt <= now_local

    def translate_title_ja_to_ko(self, text_ja: str) -> str | None:
        if not text_ja or not self.translator:
            return None
        try:
            result = self.translator.translate(text_ja, src="ja", dest="ko")
            return result.text
        except Exception as e:
            self.logger.error(f"구글 번역(무료 API) 중 오류 발생: {e}")
            return None

    def clean_title_jp(self, raw_title: str) -> str:
        if not raw_title:
            return ""
        return re.sub(r"\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}.*$", "", raw_title).strip()

    # --- 일본 ZDNet (software) ---
    def extract_new_articles_jp_list(self, html: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        header = soup.find(lambda tag: tag.name in ["h2", "h3"] and tag.get_text(strip=True).startswith("新着"))
        if not header:
            self.logger.warning("[JP] 新着 섹션을 찾을 수 없습니다.")
            return []

        articles = []
        for sibling in header.find_next_siblings():
            if sibling.name in ["h2", "h3"]:
                break
            for a in sibling.find_all("a", href=True):
                title = a.get_text(strip=True)
                if not title or len(title) < 8:
                    continue
                url = urljoin(base_url, a["href"])
                articles.append({
                    "source": "zdnet_jp",
                    "title_ja": self.clean_title_jp(title),
                    "url": url,
                })
        return articles

    def fetch_published_at_jp(self, article_url: str) -> datetime | None:
        try:
            html = self.fetch_html(article_url)
            soup = BeautifulSoup(html, "html.parser")
            text_node = soup.find(string=re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}"))
            if not text_node:
                return None
            m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text_node)
            if not m:
                return None
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
        except Exception as e:
            self.logger.warning(f"[JP] 본문 게시 시간 획득 실패: {article_url} ({e})")
            return None

    def collect_recent_articles_jp(self) -> list[dict]:
        self.logger.info(f"[JP] 최신 소프트웨어 리스트 페이지 크롤링: {self.japan_software_url}")
        try:
            html = self.fetch_html(self.japan_software_url)
            candidates = self.extract_new_articles_jp_list(html, self.japan_software_url)
            recent = []
            for item in candidates:
                url = item["url"]
                dt = self.fetch_published_at_jp(url)
                if not dt:
                    continue
                item["published_at"] = dt
                if self.is_within_last_24h(dt):
                    recent.append(item)
            self.logger.info(f"[JP] 24시간 내 신규 기사 {len(recent)}개 감지")
            return recent
        except Exception as e:
            self.logger.error(f"[JP] 크롤링 오류: {e}")
            return []

    # --- 한국 ZDNet (AI) ---
    def extract_new_articles_kr_ai_list(self, html: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        header = soup.find(lambda tag: tag.name in ["h2", "h3"] and "인공지능 최신뉴스" in tag.get_text())
        if not header:
            self.logger.warning("[KR] '인공지능 최신뉴스' 섹션을 찾을 수 없습니다.")
            return []

        articles = []
        for sibling in header.find_next_siblings():
            if sibling.name in ["h2", "h3"] and "지금 뜨는 기사" in sibling.get_text():
                break
            for a in sibling.find_all("a", href=True):
                href = a["href"]
                if "/view/?no=" not in href:
                    continue
                title = a.get_text(strip=True)
                if not title:
                    continue
                url = urljoin(base_url, href)
                articles.append({
                    "source": "zdnet_kr_ai",
                    "title_ko": title,
                    "url": url,
                })
        return articles

    def fetch_published_at_kr(self, article_url: str) -> datetime | None:
        try:
            html = self.fetch_html(article_url)
            soup = BeautifulSoup(html, "html.parser")
            text_node = soup.find(string=re.compile(r"입력\s*:?\s*\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}"))
            if not text_node:
                return None
            m = re.search(r"입력\s*:?\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})", text_node)
            if not m:
                return None
            return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M")
        except Exception as e:
            self.logger.warning(f"[KR] 본문 게시 시간 획득 실패: {article_url} ({e})")
            return None

    def collect_recent_articles_kr_ai(self) -> list[dict]:
        self.logger.info(f"[KR] AI 최신 리스트 페이지 크롤링: {self.korea_ai_url}")
        try:
            html = self.fetch_html(self.korea_ai_url)
            candidates = self.extract_new_articles_kr_ai_list(html, self.korea_ai_url)
            recent = []
            for item in candidates:
                url = item["url"]
                dt = self.fetch_published_at_kr(url)
                if not dt:
                    continue
                item["published_at"] = dt
                if self.is_within_last_24h(dt):
                    recent.append(item)
            self.logger.info(f"[KR] 24시간 내 신규 기사 {len(recent)}개 감지")
            return recent
        except Exception as e:
            self.logger.error(f"[KR] 크롤링 오류: {e}")
            return []

    def format_telegram_message(self, item: dict) -> str:
        source = item.get("source", "")
        url = item.get("url", "")
        published_at = item.get("published_at")
        
        if source == "zdnet_jp":
            title_ja = item.get("title_ja", "(제목 없음)")
            title_ko = item.get("title_ko", "(번역 실패)")
            text = (
                f"🇯🇵 ZDNet Japan (Software)\n"
                f"📰 원문 제목(JP): {title_ja}\n"
                f"🇰🇷 번역 제목(KO): {title_ko}\n"
            )
        elif source == "zdnet_kr_ai":
            title_ko = item.get("title_ko", "(제목 없음)")
            text = f"🇰🇷 ZDNet Korea (AI)\n📰 제목: {title_ko}\n"
        else:
            title = item.get("title", "(제목 없음)")
            text = f"📰 ZDNet\n제목: {title}\n"

        if isinstance(published_at, datetime):
            text += f"🕒 기사 시각: {published_at.strftime('%Y-%m-%d %H:%M')}\n"
        text += f"🔗 URL: {url}"
        return text

    def run(self, tg_token=None, tg_chat_id=None):
        # 환경변수 호환성 보장
        token = tg_token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        chat_id = tg_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_TOKEN(혹은 TELEGRAM_BOT_TOKEN) / TELEGRAM_CHAT_ID 설정이 누락되었습니다.")

        # 기사 목록 크롤링
        jp_articles = self.collect_recent_articles_jp()
        kr_articles = self.collect_recent_articles_kr_ai()
        all_candidates = jp_articles + kr_articles

        new_items = []
        for item in all_candidates:
            url = item["url"]
            if self.is_seen(url):
                continue

            if item.get("source") == "zdnet_jp":
                ja_title = item.get("title_ja")
                item["title_ko"] = self.translate_title_ja_to_ko(ja_title)

            new_items.append(item)

        if not new_items:
            self.logger.info("새로 발행된 기사가 없습니다.")
            return 0

        self.logger.info(f"신규 기사 {len(new_items)}개 발견, 전송 시작...")
        for item in new_items:
            msg = self.format_telegram_message(item)
            self.send_telegram_text(token, chat_id, msg)
            self.mark_seen(item["url"], item.get("title_ko") or item.get("title_ja"))
            time.sleep(1)

        return len(new_items)
