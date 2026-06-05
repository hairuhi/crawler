import os
import re
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler

class EtolandCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("etoland")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; EtolandYakhuOnly/1.7)",
            "Accept-Language": "ko,ko-KR;q=0.9,en;q=0.8",
            "Referer": "https://www.etoland.co.kr/",
        })
        self.timeout = 20
        self.hgall_url = "https://www.etoland.co.kr/bbs/hgall.php?bo_table=etohumor07&sca=%BE%E0%C8%C4"
        self.target_board = "etohumor07"
        
        # 설정 초기화
        self.download_and_upload = os.getenv("DOWNLOAD_AND_UPLOAD", "0").strip() == "1"
        self.trace_image_debug = os.getenv("TRACE_IMAGE_DEBUG", "0").strip() == "1"
        self.force_send_latest = os.getenv("FORCE_SEND_LATEST", "0").strip() == "1"
        self.enable_heartbeat = os.getenv("ENABLE_HEARTBEAT", "0").strip() == "1"
        self.heartbeat_text = os.getenv("HEARTBEAT_TEXT", "🧪 Heartbeat: bot alive.")

        # 제외할 이미지 패턴
        self.exclude_image_substrings = [
            "link.php?", "/logo/", "/banner/", "/ads/", "/noimage",
            "/favicon", "/thumb/", "/placeholder/", "/img/icon_link.gif",
            "icon_link.gif", "/img/loading_img.jpg", "loading_img.jpg"
        ]
        extra_excludes = os.getenv("EXCLUDE_IMAGE_SUBSTRINGS", "").strip()
        if extra_excludes:
            self.exclude_image_substrings += [s.strip() for s in extra_excludes.split(",") if s.strip()]

        self.placeholder_icon_names = {"icon_link.gif", "loading_img.jpg"}

    def is_placeholder_image(self, url: str) -> bool:
        try:
            path = urlparse(url).path.lower()
            filename = path.rsplit("/", 1)[-1]
            return (
                filename in self.placeholder_icon_names
                or "/img/icon_link.gif" in path
                or "/img/loading_img.jpg" in path
            )
        except Exception:
            return False

    def is_excluded_image(self, url: str) -> bool:
        low = url.lower()
        return any(hint.lower() in low for hint in self.exclude_image_substrings)

    def get_encoding_safe_text(self, resp: requests.Response) -> str:
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ansi_x3.4-1968"):
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def absolutize(self, base: str, url: str) -> str:
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        return urljoin(base, url)

    def text_summary_from_html(self, soup: BeautifulSoup, max_chars=280) -> str:
        cands = ["#bo_v_con", ".bo_v_con", "div.view_content", ".viewContent", "#view_content", "article"]
        cont = next((soup.select_one(s) for s in cands if soup.select_one(s)), soup)
        for t in cont(["script", "style", "noscript"]): t.extract()
        text = re.sub(r"\s+", " ", cont.get_text(" ", strip=True)).strip()
        return text[:max_chars-1]+"…" if len(text)>max_chars else text

    def fetch_hgall_yakhu_list(self) -> list[dict]:
        r = self.session.get(self.hgall_url, timeout=self.timeout)
        soup = BeautifulSoup(self.get_encoding_safe_text(r), "html.parser")
        posts = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "wr_id=" not in href: continue
            m = re.search(r"wr_id=(\d+)", href)
            if not m: continue
            wr_id = int(m.group(1))
            bo = self.target_board
            b = re.search(r"bo_table=([a-z0-9_]+)", href, re.I)
            if b: bo = b.group(1).lower()
            if bo != self.target_board: continue
            t = a.get_text(strip=True)
            if not t: continue
            posts.append({"bo_table": bo, "wr_id": wr_id, "title": t, "url": self.absolutize(self.hgall_url, href)})
        posts = sorted({(p["bo_table"], p["wr_id"]): p for p in posts}.values(), key=lambda x: x["wr_id"], reverse=True)
        self.logger.info(f"약후 리스트 수집 완료: {len(posts)}개")
        return posts

    def fetch_content_media_and_summary(self, post_url: str) -> dict:
        r = self.session.get(post_url, timeout=self.timeout)
        soup = BeautifulSoup(self.get_encoding_safe_text(r), "html.parser")
        summary = self.text_summary_from_html(soup)
        cont = next((soup.select_one(s) for s in ["#bo_v_con", ".bo_v_con", "div.view_content", ".viewContent", "#view_content", "article"] if soup.select_one(s)), soup)
        all_imgs = [self.absolutize(post_url, img.get("src") or "") for img in cont.find_all("img") if img.get("src")]
        
        images = []
        for u in all_imgs:
            if self.is_placeholder_image(u): continue
            if not self.is_excluded_image(u): images.append(u)
        if not images:
            for a in cont.find_all("a", href=True):
                href = a["href"].strip()
                if re.search(r"\.(jpg|jpeg|png|gif|webp)(?:\?|$)", href, re.I):
                    full = self.absolutize(post_url, href)
                    if self.is_placeholder_image(full): continue
                    if not self.is_excluded_image(full): images.append(full)
                    
        videos = [self.absolutize(post_url, v.get("src")) for v in cont.find_all(["video", "source"]) if v.get("src")]
        iframes = [self.absolutize(post_url, f.get("src")) for f in cont.find_all("iframe") if f.get("src")]
        title = (soup.find("meta", property="og:title") or {}).get("content") or (soup.title.string.strip() if soup.title else "")
        return {"images": images, "videos": videos, "iframes": iframes, "summary": summary, "title_override": title}

    def build_caption(self, title: str, url: str, summary: str) -> str:
        cap = f"📌 <b>{title}</b>"
        if summary:
            cap += f"\n{summary}"
        cap += f"\n{url}"
        return cap[:900]

    def run(self, tg_token=None, tg_chat_id=None):
        token = tg_token or os.getenv("TELEGRAM_TOKEN")
        chat_id = tg_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID가 필요합니다.")

        if self.enable_heartbeat:
            self.send_telegram_text(token, chat_id, self.heartbeat_text)

        posts = self.fetch_hgall_yakhu_list()
        posts.sort(key=lambda x: x["wr_id"])
        
        to_send = []
        for p in posts:
            k = f"etoland:{p['bo_table']}:{p['wr_id']}"
            if not self.is_seen(k):
                p["_seen_key"] = k
                to_send.append(p)
                
        if self.force_send_latest and not to_send and posts:
            latest = sorted(posts, key=lambda x: x["wr_id"], reverse=True)[0]
            latest["_seen_key"] = f"etoland:{latest['bo_table']}:{latest['wr_id']}"
            to_send = [latest]

        if not to_send:
            self.logger.info("새로운 게시글이 없습니다.")
            return 0

        self.logger.info(f"전송할 새로운 게시글 {len(to_send)}개 발견")
        count = 0
        for p in to_send:
            title = p["title"]
            url = p["url"]
            try:
                m = self.fetch_content_media_and_summary(url)
                if m.get("title_override"):
                    title = m["title_override"]
                imgs, vids, ifr, summary = m["images"], m["videos"], m["iframes"], m["summary"]
                cap = self.build_caption(title, url, summary)
                
                self.send_telegram_text(token, chat_id, cap)
                time.sleep(1)
                
                self.logger.info(f"미디어 전송 시작 (wr_id={p['wr_id']}): 이미지 {len(imgs)}개, 비디오 {len(vids)}개, 임베드 {len(ifr)}개")
                for i in imgs:
                    self.send_telegram_media(token, chat_id, "photo", i, referer=url, download_and_upload=self.download_and_upload)
                    time.sleep(1)
                for v in vids:
                    self.send_telegram_media(token, chat_id, "video", v, referer=url, download_and_upload=self.download_and_upload)
                    time.sleep(1)
                if ifr:
                    self.send_telegram_text(token, chat_id, "🎥 임베드:\n" + "\n".join(ifr[:5]))
                    time.sleep(1)
                
                self.mark_seen(p["_seen_key"])
                count += 1
            except Exception as e:
                self.logger.error(f"게시글 처리 중 오류 발생 (wr_id={p['wr_id']}): {e}")
        return count
