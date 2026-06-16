import os
import re
import hashlib
import requests
import psycopg2
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

class NewsAggregator:
    def __init__(self):
        self.db_params = {
            "host": "localhost", "port": "15432",
            "database": "app", "user": "postgres", "password": "0000"
        }
        self.tokens = {
            "CRYPTOPANIC": os.getenv('CRYPTOPANIC_TOKEN'),
            "ALPHAVANTAGE": os.getenv('ALPHA_VANTAGE_API_KEY')
        }
        self.split_date = datetime(2026, 1, 20, tzinfo=timezone.utc)

    def _parse_date(self, date_str):
        if not date_str: return None
        try:
            if len(date_str) == 15 and 'T' in date_str:
                return datetime.strptime(date_str, '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        except:
            return None

    def _get_db_categories(self, limit_top_4=False):
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()
            if limit_top_4:
                target_tickers = ('BTC', 'ETH', 'XRP', 'SOL')
                cur.execute("SELECT symbol, category_name, category_id FROM public.category WHERE symbol IN %s", (target_tickers,))
            else:
                cur.execute("SELECT symbol, category_name, category_id FROM public.category")
            
            categories = [{'symbol': r[0].strip().upper(), 'name': r[1].strip().upper(), 'id': r[2]} for r in cur.fetchall()]
            cur.close()
            conn.close()
            return categories
        except Exception as e:
            print(f"⚠️ 카테고리 로드 실패: {e}")
            return []

    # [중요 변경] 테이블 종류에 따라 저장 로직 분기
    def _save_batch(self, items, source, table_name="news_data"):
        if not items: return
        conn = None
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()
            inserted_count = 0

            for item in items:
                # 1. 공통 필드 추출
                title = item.get('title', '')
                symbol = item.get('assigned_symbol', '')
                category_id = item.get('assigned_category_id')
                description = item.get('description') or item.get('summary', '')
                dt = self._parse_date(item.get('time_published') or item.get('created_at'))
                
                if not dt: continue
                is_test = dt >= self.split_date
                date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                hash_key = hashlib.md5(f"{title.strip()}_{date_str}_{symbol}".encode()).hexdigest()

                # 2. 테이블별 쿼리 분기
                if table_name == "community_data":
                    # community_data 전용 필드 처리
                    # platform: kind 값 사용 (media, blog 등), 없으면 'unknown'
                    platform = item.get('kind', 'unknown')
                    
                    # ups: votes 딕셔너리에서 liked나 positive 값 추출
                    votes = item.get('votes', {})
                    ups = votes.get('liked', 0) if isinstance(votes, dict) else 0
                    if ups == 0 and isinstance(votes, dict):
                         ups = votes.get('positive', 0)

                    query = """
                    INSERT INTO public.community_data
                    (category_id, title, description, published_at, symbol, hash_key, is_test, platform, ups) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hash_key) DO NOTHING;
                    """
                    cur.execute(query, (category_id, title, description, dt, symbol, hash_key, is_test, platform, ups))

                else:
                    # news_data (기본)
                    query = """
                    INSERT INTO public.news_data
                    (category_id, title, description, published_at, symbol, hash_key, is_test) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hash_key) DO NOTHING;
                    """
                    cur.execute(query, (category_id, title, description, dt, symbol, hash_key, is_test))
                
                if cur.rowcount > 0: inserted_count += 1

            conn.commit()
            if inserted_count > 0:
                print(f"💾 [{source}] -> [{table_name}] {inserted_count}건 저장 완료")
        except Exception as e:
            if conn: conn.rollback()
            print(f"❌ DB 저장 에러 ({table_name}): {e}")
        finally:
            if conn: conn.close()

    def fetch_alpha_vantage(self, start_time=None, end_time=None):
        # AlphaVantage는 전부 news_data로 저장
        categories = self._get_db_categories(limit_top_4=(start_time is None))
        if not categories or not self.tokens["ALPHAVANTAGE"]: return

        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&limit=1000&apikey={self.tokens['ALPHAVANTAGE']}"
        if start_time: url += f"&time_from={start_time}"
        if end_time: url += f"&time_to={end_time}"
        
        try:
            print(f"📡 AlphaVantage 요청: {start_time} ~ {end_time}")
            res = requests.get(url)
            data = res.json()
            articles = data.get('feed', [])
            
            matched_list = []
            for art in articles:
                title = (art.get('title') or '').upper()
                av_tickers = [t.get('ticker', '').replace("CRYPTO:", "").upper() for t in art.get('ticker_sentiment', [])]
                for cat in categories:
                    if cat['symbol'] in av_tickers or re.search(rf"\b{cat['symbol']}\b", title) or re.search(rf"\b{cat['name']}\b", title):
                        item = art.copy()
                        item['assigned_symbol'] = cat['symbol']
                        item['assigned_category_id'] = cat['id']
                        matched_list.append(item)
            
            self._save_batch(matched_list, "AlphaVantage", "news_data")
        except Exception as e: print(f"❌ AV 에러: {e}")

    def fetch_cryptopanic(self, target_date_limit=None):
        categories = self._get_db_categories(limit_top_4=(target_date_limit is None))
        
        url = "https://cryptopanic.com/api/developer/v2/posts/"
        
        # [핵심] kind 필터 없음 -> 모든 데이터 수신
        params = {"auth_token": self.tokens["CRYPTOPANIC"], "regions": "en"}
        
        page_count = 0
        
        print(f"📡 [CryptoPanic] 통합 수집 시작 (News -> news_data / Media -> community_data)...")

        while url:
            try:
                page_count += 1
                res = requests.get(url, params=params)
                
                if res.status_code != 200:
                    print(f"⚠️ 요청 실패: {res.status_code}")
                    break

                data = res.json()
                articles = data.get('results', [])
                
                if not articles:
                    print(f"✅ 더 이상 데이터가 없습니다. (Page {page_count})")
                    break

                news_batch = []      # news_data 적재용
                community_batch = [] # community_data 적재용
                
                stop_fetching = False

                for art in articles:
                    published_at = self._parse_date(art.get('created_at'))
                    
                    if target_date_limit and published_at and published_at < target_date_limit:
                        stop_fetching = True
                        continue

                    # 데이터 종류 확인 (news, media, blog 등)
                    kind = art.get('kind', 'news')
                    title = art.get('title', '').strip()
                    title_upper = title.upper()
                    cp_currencies = [c.get('code', '').upper() for c in art.get('currencies', [])]

                    # 카테고리 매칭
                    matched_cat = None
                    for cat in categories:
                        if (cat['symbol'] in cp_currencies) or \
                           (re.search(rf"\b{cat['symbol']}\b", title_upper)) or \
                           (re.search(rf"\b{cat['name']}\b", title_upper)):
                            matched_cat = cat
                            break 
                    
                    if matched_cat:
                        item = art.copy()
                        item['assigned_symbol'] = matched_cat['symbol']
                        item['assigned_category_id'] = matched_cat['id']
                        
                        # [분기 처리]
                        if kind == 'news':
                            news_batch.append(item)
                        else:
                            # 커뮤니티 데이터 리스트에 추가
                            community_batch.append(item)
                
                # DB 저장 실행 (각각 다른 테이블로)
                if news_batch:
                    self._save_batch(news_batch, f"CryptoPanic-News-P{page_count}", "news_data")
                
                if community_batch:
                    self._save_batch(community_batch, f"CryptoPanic-Comm-P{page_count}", "community_data")
                
                # 진행 로그
                if not news_batch and not community_batch:
                     print(f"🕸️ [P{page_count}] 수집 {len(articles)}건 -> 매칭 0건")

                next_url = data.get('next')
                if stop_fetching:
                    print(f"🛑 목표 날짜 도달. 종료.")
                    break
                
                if not next_url:
                    break

                url = next_url
                params = {}
                if "auth_token" not in url:
                    params["auth_token"] = self.tokens["CRYPTOPANIC"]
                
                time.sleep(1)

            except Exception as e:
                print(f"❌ 에러: {e}")
                break