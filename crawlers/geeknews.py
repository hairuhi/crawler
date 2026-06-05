import os
import time
import requests
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler

class GeeknewsCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("geeknews")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        self.target_url = "https://news.hada.io/new"

    def fetch_recent_topics(self) -> list[dict]:
        self.logger.info(f"GeekNews 최신 토픽 목록 크롤링 시작: {self.target_url}")
        resp = requests.get(self.target_url, headers=self.headers, timeout=20)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        topics = []
        
        rows = soup.select(".topic_row")
        for row in rows:
            topic_id = row.get("data-topic-state-id")
            if not topic_id:
                continue
                
            # 제목 추출
            title_el = row.select_one(".topic-title-heading")
            title = title_el.get_text(strip=True) if title_el else ""
            
            # 원문 URL 추출
            link_el = row.select_one(".topictitle a")
            ext_url = link_el.get("href") if link_el else ""
            
            # 상세 내용 설명 추출
            desc_el = row.select_one(".topicdesc a")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            
            # 등록 시간 속성 추출
            time_el = row.select_one("time.js-relative-time")
            dt_str = time_el.get("datetime") if time_el else ""
            
            # 긱뉴스 자체 상세/토론 URL
            detail_url = f"https://news.hada.io/topic?id={topic_id}"
            
            topics.append({
                "id": topic_id,
                "title": title,
                "url": ext_url or detail_url,
                "detail_url": detail_url,
                "desc": desc,
                "time_str": dt_str
            })
            
        return topics

    def run(self, tg_token=None, tg_chat_id=None):
        token = tg_token or os.getenv("TELEGRAM_TOKEN")
        chat_id = tg_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 설정이 누락되었습니다.")
            
        topics = self.fetch_recent_topics()
        # 토픽 ID를 기준으로 오름차순 정렬하여 가장 오래된 글부터 처리
        topics.sort(key=lambda x: int(x["id"]))
        
        new_items = []
        for t in topics:
            k = f"geeknews:{t['id']}"
            if not self.is_seen(k):
                new_items.append(t)
                
        if not new_items:
            self.logger.info("새로운 GeekNews 게시글이 없습니다.")
            return 0
            
        self.logger.info(f"새로운 GeekNews 게시글 {len(new_items)}개 감지, 전송 시작...")
        count = 0
        for t in new_items:
            msg = (
                f"🤓 <b>GeekNews 새 소식</b>\n"
                f"📰 <b>{t['title']}</b>\n\n"
                f"{t['desc']}\n\n"
                f"🔗 원문: {t['url']}\n"
                f"💬 토론: {t['detail_url']}"
            )
            
            self.send_telegram_text(token, chat_id, msg)
            self.mark_seen(f"geeknews:{t['id']}", t['title'])
            time.sleep(1)
            count += 1
            
        return count
