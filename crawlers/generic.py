import os
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler

class GenericCrawler(BaseCrawler):
    def __init__(self, config: dict):
        """
        config = {
            "name": "크롤러이름",
            "url": "대상 홈페이지 URL",
            "item_selector": "게시글 아이템 감싸는 부모 CSS 선택자",
            "title_selector": "제목 태그 CSS 선택자",
            "link_selector": "링크 태그 CSS 선택자",
            "desc_selector": "요약/설명 태그 CSS 선택자"
        }
        """
        super().__init__(f"generic_{config['name']}")
        self.config = config
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    def fetch_items(self) -> list[dict]:
        """설정된 선택자를 기반으로 웹페이지 요소들을 파싱하여 리스트로 반환합니다."""
        url = self.config["url"]
        item_sel = self.config.get("item_selector")
        title_sel = self.config.get("title_selector")
        link_sel = self.config.get("link_selector")
        desc_sel = self.config.get("desc_selector")

        self.logger.info(f"범용 크롤링 웹 요청 시작: {url}")
        resp = requests.get(url, headers=self.headers, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        if not item_sel:
            self.logger.warning("item_selector가 설정되지 않았습니다.")
            return items

        # 게시물 목록 블록 긁기
        rows = soup.select(item_sel)
        for i, row in enumerate(rows):
            # 1. 제목 파싱
            title = ""
            if title_sel:
                t_el = row.select_one(title_sel)
                if t_el:
                    title = t_el.get_text(strip=True)
            if not title:
                # 선택자가 없거나 비어있는 경우, 본문 텍스트 슬라이싱
                title = row.get_text(" ", strip=True)[:60] + "..."

            # 2. 링크 파싱
            link = ""
            if link_sel:
                l_el = row.select_one(link_sel)
                if l_el:
                    link = l_el.get("href", "").strip()
            if not link:
                # 폴백: 해당 블록 내 첫 번째 a 태그 검색
                first_a = row.find("a")
                if first_a:
                    link = first_a.get("href", "").strip()
            
            # 절대 경로 보장
            if link:
                link = urljoin(url, link)
            else:
                link = url

            # 3. 요약 내용 파싱
            desc = ""
            if desc_sel:
                d_el = row.select_one(desc_sel)
                if d_el:
                    desc = d_el.get_text(strip=True)

            items.append({
                "index": i,
                "title": title,
                "url": link,
                "desc": desc
            })

        self.logger.info(f"파싱 완료: {len(items)}개의 아이템 검출")
        return items

    def run(self, tg_token=None, tg_chat_id=None):
        token = tg_token or os.getenv("TELEGRAM_TOKEN")
        chat_id = tg_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 설정이 필요합니다.")

        items = self.fetch_items()
        
        # 목록 아래(오래된 항목)부터 위로 전송되도록 정렬 뒤집기
        items.reverse()
        
        new_items_count = 0
        for item in items:
            # 키는 고유해야 하므로 크롤러이름과 URL 주소 조합
            k = f"generic:{self.config['name']}:{item['url']}"
            if not self.is_seen(k):
                msg = (
                    f"🔔 <b>[알림] {self.config['name']} 새 글</b>\n"
                    f"📰 <b>{item['title']}</b>\n\n"
                )
                if item["desc"]:
                    msg += f"{item['desc']}\n\n"
                msg += f"🔗 바로가기: {item['url']}"

                self.send_telegram_text(token, chat_id, msg)
                self.mark_seen(k, item['title'])
                time.sleep(1)
                new_items_count += 1

        return new_items_count
