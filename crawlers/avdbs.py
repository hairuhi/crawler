import os
import time
import logging
import requests
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None
    
from crawlers.base import BaseCrawler

class AvdbsCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("avdbs")
        self.boards = [
            {"name": "T50", "url": "https://www.avdbs.com/board/t50"},
            {"name": "T22", "url": "https://www.avdbs.com/board/t22"}
        ]

    def run(self, tg_token=None, tg_chat_id=None, avdbs_id=None, avdbs_pw=None):
        token = tg_token or os.getenv("TELEGRAM_TOKEN")
        chat_id = tg_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        user_id = avdbs_id or os.getenv("AVDBS_ID")
        user_pw = avdbs_pw or os.getenv("AVDBS_PW")

        if not all([token, chat_id, user_id, user_pw]):
            raise RuntimeError("AVDBS_ID, AVDBS_PW, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 설정이 누락되었습니다.")

        self.logger.info("Playwright 웹 브라우저 기동 중...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.new_page()
                if stealth_sync:
                    stealth_sync(page)

                # 로그인 처리
                login_url = "https://www.avdbs.com/menu/member/login.php"
                self.logger.info(f"로그인 페이지로 이동: {login_url}")
                page.goto(login_url, timeout=60000)
                page.wait_for_load_state("networkidle")

                if page.is_visible("#member_uid"):
                    self.logger.info("로그인 정보를 입력하고 있습니다...")
                    page.fill("#member_uid", user_id)
                    page.fill("#member_pwd", user_pw)
                    with page.expect_navigation(timeout=60000):
                        page.click(".btn_login")
                    page.wait_for_load_state("networkidle")

                    if "login.php" in page.url or page.is_visible("#member_uid"):
                        self.logger.error("로그인 실패 (아이디/비밀번호 확인 필요)")
                        self.send_telegram_text(token, chat_id, "❌ AVDBS Crawler 로그인 실패. 계정 정보를 확인하세요.")
                        return 0
                    self.logger.info("로그인 성공!")
                else:
                    self.logger.warning("로그인 입력 필드를 찾을 수 없습니다. 이미 로그인되어 있거나 차단되었을 수 있습니다.")
                    return 0

                # 세션 쿠키 추출
                session_cookies = context.cookies()
                req_cookies = {c['name']: c['value'] for c in session_cookies}

                # 게시판 순회
                new_posts_count = 0
                for board in self.boards:
                    self.logger.info(f"[{board['name']}] 게시판 스캔 시작")
                    page.goto(board['url'], timeout=60000)
                    page.wait_for_load_state("networkidle")

                    if "Access Denied" in page.title() or "Cloudflare" in page.title():
                        self.logger.error(f"[{board['name']}] 접속이 차단되었습니다 (Cloudflare/Access Denied)")
                        continue

                    if "로그인" in page.title():
                        self.logger.error("로그인 세션이 유실되었습니다.")
                        continue

                    # 게시글 링크들 긁기
                    links = page.query_selector_all("a.lnk.vstt")
                    board_posts = []

                    for link in links:
                        # 공지사항 필터링
                        is_notice = link.evaluate("el => el.querySelector('h2 img.notice') !== null")
                        if is_notice:
                            continue

                        href = link.get_attribute("href")
                        if not href:
                            continue
                        
                        full_url = href if href.startswith("http") else f"https://www.avdbs.com{href}"
                        
                        if self.is_seen(full_url):
                            continue

                        title_el = link.query_selector("h2")
                        title = title_el.inner_text().strip() if title_el else link.inner_text().strip()
                        board_posts.append({"title": title, "url": full_url})
                        
                        if len(board_posts) >= 5: # 스팸 방지를 위해 한 실행당 최대 5개 제한
                            break

                    self.logger.info(f"[{board['name']}] 신규 게시글 {len(board_posts)}개 추출 완료")

                    for post in board_posts:
                        self.logger.info(f"신규 글 파싱 중: {post['title']}")
                        
                        page.goto(post['url'], timeout=60000)
                        page.wait_for_load_state("domcontentloaded")

                        if "로그인" in page.title():
                            self.logger.error("게시글 이동 중 로그인 세션 만료")
                            continue

                        # 본문 내 이미지/비디오 URL 추출
                        media_urls = []
                        imgs = page.query_selector_all(".view_content img, #bo_v_con img")
                        for img in imgs:
                            src = img.get_attribute("data-original") or img.get_attribute("data-src") or img.get_attribute("src")
                            if src:
                                full_src = src if src.startswith("http") else f"https://www.avdbs.com{src}"
                                if any(x in full_src for x in ["blank.gif", "loading", "icon"]):
                                    continue
                                media_urls.append(full_src)

                        vids = page.query_selector_all("video source")
                        for v in vids:
                            src = v.get_attribute("src")
                            if src:
                                full_src = src if src.startswith("http") else f"https://www.avdbs.com{src}"
                                media_urls.append(full_src)

                        # 중복 제거
                        media_urls = list(set(media_urls))
                        self.logger.info(f"미디어 URL {len(media_urls)}개 발견")

                        # 1단계: 텍스트 알림 발송
                        msg_text = f"[{board['name']}] <b>{post['title']}</b>\n<a href='{post['url']}'>{post['url']}</a>"
                        self.send_telegram_text(token, chat_id, msg_text)
                        time.sleep(1)

                        # 2단계: 미디어 파일 발송 (최대 10개)
                        for url in media_urls[:10]:
                            m_type = "video" if any(url.split("?")[0].lower().endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm']) else "photo"
                            self.send_telegram_media(
                                token, chat_id, m_type, url,
                                referer=post['url'],
                                download_and_upload=True
                            )
                            time.sleep(1)

                        self.mark_seen(post['url'], post['title'])
                        new_posts_count += 1
                        
                browser.close()
                return new_posts_count
        except Exception as e:
            self.logger.error(f"AVDBS 크롤러 실행 오류: {e}")
            self.send_telegram_text(token, chat_id, f"❌ AVDBS 크롤러 실행 중 에러가 발생했습니다: {e}")
            return 0
