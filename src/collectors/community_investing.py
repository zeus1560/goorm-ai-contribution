import time
import re
import random
import hashlib
import psycopg2
import logging
import json
import os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# [설정] 로그 파일
logging.basicConfig(
    filename='crawler_crypto_final.log', 
    filemode='a', 
    level=logging.INFO, 
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

def log(message):
    print(message)
    logging.info(message)

PROGRESS_FILE = 'crawler_progress.json'

db_config = {
    "user": "postgres",
    "password": "0000",
    "database": "app", 
    "host": "localhost",
    "port": 15432
}

TARGET_CUTOFF_DATE = datetime(2025, 10, 1)

# DOT은 페이지 없음 이슈로 제외
TARGET_LIST = [
    ("BTC", "https://kr.investing.com/crypto/bitcoin/chat"),
    ("ETH", "https://kr.investing.com/crypto/ethereum/chat"),
    ("XRP", "https://kr.investing.com/crypto/xrp/chat"),
    ("SOL", "https://kr.investing.com/crypto/solana/chat"),
    ("ADA", "https://kr.investing.com/crypto/cardano/chat"),
    ("DOGE", "https://kr.investing.com/crypto/dogecoin/chat"),
    ("TRX", "https://kr.investing.com/crypto/tron/chat"),
    ("LTC", "https://kr.investing.com/crypto/litecoin/chat"),
    ("SHIB", "https://kr.investing.com/crypto/shiba-inu/chat"),
    ("MATIC", "https://kr.investing.com/crypto/polygon/chat"),
    ("AVAX", "https://kr.investing.com/crypto/avalanche/chat"),
    ("UNI", "https://kr.investing.com/crypto/uniswap/chat"),
    ("LINK", "https://kr.investing.com/crypto/chainlink/chat"),
    ("ATOM", "https://kr.investing.com/crypto/cosmos/chat"),
    ("FIL", "https://kr.investing.com/crypto/filecoin/chat"),
]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_progress(symbol, page_num):
    data = load_progress()
    data[symbol] = page_num
    with open(PROGRESS_FILE, 'w') as f: json.dump(data, f)

def get_start_page(symbol):
    return load_progress().get(symbol, 1)

def get_db_connection():
    try: return psycopg2.connect(**db_config)
    except: return None

def generate_hash_key(symbol, user, date_obj, content):
    date_str = date_obj.strftime("%Y%m%d%H%M") 
    raw_str = f"investing_{symbol}_{user}_{date_str}_{content}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def parse_investing_date(date_text):
    if not date_text: return None
    now = datetime.now()
    text = date_text.strip().replace(" ", "")
    try:
        if "방금" in text: return now
        if "분전" in text:
            minutes = int(re.search(r'(\d+)', text).group(1))
            return now - timedelta(minutes=minutes)
        if "시간전" in text:
            hours = int(re.search(r'(\d+)', text).group(1))
            return now - timedelta(hours=hours)
        
        nums = re.findall(r'\d+', text)
        nums = [int(n) for n in nums]
        if len(nums) >= 5: return datetime(nums[0], nums[1], nums[2], nums[3], nums[4])
        elif len(nums) >= 3: return datetime(nums[0], nums[1], nums[2])
        return None
    except: return None

def inject_stealth_scripts(page):
    page.add_style_tag(content="""
        header, nav, iframe, .ad-unit, .sticky-header, #PromoteSignUpPopUp,
        div[id*='google'], div[class*='popup'], footer, .rightColumn,
        .bottom-sticky-banner, #bottom_ad_wrapper, #onetrust-banner-sdk
        { display: none !important; }
    """)
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

def wait_for_challenge_solution(page):
    try:
        if page.locator("text=사람인지 확인하는 중입니다").count() > 0 or \
           page.locator("text=보안을 검토해야 합니다").count() > 0:
            log("🛡️ [보안 감지] 대기 중...")
            for _ in range(120):
                time.sleep(1)
                if page.locator("text=사람인지 확인하는 중입니다").count() == 0:
                    log("✅ 보안 해제됨.")
                    time.sleep(3)
                    return True
            return False
    except: pass
    return True

def crawl_one_coin(playwright, symbol, url):
    start_page = get_start_page(symbol)
    log(f"\n🚀 [{symbol}] 수집 시작 (시작 페이지: {start_page}p)")
    
    browser = playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
    )
    context = browser.new_context(
        viewport={'width': 1366, 'height': 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    page = context.new_page()
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        target_url = url if start_page == 1 else f"{url}/{start_page}"
        page.goto(target_url, wait_until="domcontentloaded")
        
        if not wait_for_challenge_solution(page): raise Exception("IP 차단됨")
        inject_stealth_scripts(page)
        
        try: page.locator("[data-test='comment-date']").first.wait_for(state="visible", timeout=15000)
        except: pass

        current_page = start_page
        empty_cnt = 0

        while True:
            if not wait_for_challenge_solution(page): break

            date_elements = page.locator("[data-test='comment-date']")
            count = date_elements.count()

            if count == 0:
                log(f"  ⚠️ [{symbol}] 댓글 없음.")
                if page.locator("text=No comments").count() > 0:
                    log(f"  🛑 [{symbol}] 더 이상 댓글이 없습니다. 종료.")
                    return
                empty_cnt += 1
                if empty_cnt >= 5: return
                time.sleep(2)
            else:
                empty_cnt = 0

            real_saved = 0
            min_date = None
            
            for i in range(count):
                try:
                    date_el = date_elements.nth(i)
                    clean_date = parse_investing_date(date_el.inner_text())
                    if not clean_date: continue
                    if min_date is None or clean_date < min_date: min_date = clean_date
                    
                    if clean_date < TARGET_CUTOFF_DATE:
                        log(f"🎉 [{symbol}] 목표 날짜 도달! ({clean_date})")
                        conn.commit()
                        save_progress(symbol, 1) # 완료
                        return

                    # [핵심 수정] 3단계 위로 올라가야 진짜 '댓글 박스'를 잡습니다.
                    wrapper = date_el.locator("xpath=../../..")
                    
                    try:
                        user = wrapper.locator("a").first.inner_text().strip()
                    except:
                        user = "Unknown"

                    # [핵심 수정] .break-words가 이제 정확히 잡힐 것입니다.
                    content_el = wrapper.locator(".break-words").first
                    if content_el.count() == 0: 
                        # 혹시라도 없으면 div의 텍스트라도 긁음
                        content_el = wrapper.locator("div").last 
                    
                    content = content_el.inner_text().strip()

                    # 내용이 비었으면 스킵
                    if not content: continue

                    hash_key = generate_hash_key(symbol, user, clean_date, content)
                    sql = """
                        INSERT INTO public.community_data 
                        (title, description, published_at, symbol, platform, hash_key, ups, is_test)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (hash_key) DO NOTHING
                    """
                    cur.execute(sql, (user, content, clean_date, symbol, 'investing', hash_key, 0, False))
                    if cur.rowcount > 0: real_saved += 1
                except: continue
            
            conn.commit()
            save_progress(symbol, current_page + 1)
            date_str = min_date.strftime('%Y-%m-%d') if min_date else "Unknown"
            
            log(f"  ✅ [{symbol}] {current_page}p: {real_saved}건 저장 | {date_str}")

            target_page_num = current_page + 1
            js_script = f"""() => {{
                const container = document.querySelector('div.flex.select-none.justify-between');
                if (!container) return false;
                const btns = Array.from(container.querySelectorAll('button'));
                let target = btns.find(b => b.innerText.trim() === '{target_page_num}');
                if (!target) {{
                    target = btns.find(b => b.innerText.includes('다음') || b.innerText.includes('Next'));
                    if (!target && btns.length > 0) target = btns[btns.length - 1];
                }}
                if (target) {{
                    target.dispatchEvent(new MouseEvent('click', {{view: window, bubbles: true, cancelable: true}}));
                    return true;
                }}
                return false;
            }}"""
            
            time.sleep(random.uniform(4.0, 6.0))
            if page.evaluate(js_script):
                time.sleep(3)
                current_page += 1
            else:
                log(f"  🔥 [{symbol}] 이동 실패. 강제 이동.")
                page.goto(f"{url}/{target_page_num}", wait_until="domcontentloaded")
                time.sleep(5)
                current_page += 1

    except Exception as e:
        log(f"❌ [{symbol}] 중단: {e}")
    finally:
        if conn: conn.close()
        browser.close()
        log(f"👋 [{symbol}] 브라우저 닫음.\n")

if __name__ == "__main__":
    # 처음부터 시작하므로 진행 파일 초기화 (필요시)
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE) # 1페이지부터 다시 하기 위해 삭제

    with sync_playwright() as p:
        for symbol, url in TARGET_LIST:
            crawl_one_coin(p, symbol, url)
            time.sleep(10)
        log("✨ 전체 수집 완료!")