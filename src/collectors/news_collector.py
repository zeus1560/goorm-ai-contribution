import feedparser
import hashlib
import psycopg2
import re
import time
import schedule
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from datetime import datetime, timezone
from time import mktime
from dateutil import parser

class RssCollector:
    def __init__(self):
        self.db_params = {
            "host": "localhost", "port": "15432",
            "database": "app", "user": "postgres", "password": "0000"
        }
        
        # 벡터 DB 및 임베딩 모델 설정
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.embed_model = SentenceTransformer('intfloat/multilingual-e5-small', device=self.device)
        self.qdrant_client = QdrantClient(url="http://localhost:6333")
        self.collection_name = "news_collection"

        self.static_feeds = {
            "CoinTelegraph": "https://cointelegraph.com/rss",
            "Decrypt": "https://decrypt.co/feed",
            "BitcoinMagazine": "https://bitcoinmagazine.com/.rss/full/",
            "CryptoSlate": "https://cryptoslate.com/feed/",
            "NewsBTC": "https://www.newsbtc.com/feed/",
            "UToday": "https://u.today/rss",
            "DailyHodl": "https://dailyhodl.com/feed/",
            "Blockworks": "https://blockworks.co/feed",
            "CoinGape": "https://coingape.com/feed/",
        }

    def _get_db_categories(self):
        TARGET_WHITELIST = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'LINK']
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()
            cur.execute("SELECT symbol, category_name, category_id FROM public.category")
            rows = cur.fetchall()
            conn.close()
            cleaned = []
            if not rows: return [{'symbol': 'BTC', 'name': 'BITCOIN', 'id': 1}]
            for r in rows:
                s = r[0].strip().upper()
                if s in TARGET_WHITELIST:
                    cleaned.append({'symbol': s, 'name': r[1].strip().upper(), 'id': r[2]})
            return cleaned
        except: return []

    def _save_to_db(self, items):
        if not items: return 0
        conn = None
        saved = 0
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()
            query = """
                INSERT INTO public.news_data
                (category_id, title, description, published_at, symbol, hash_key, is_test) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hash_key) DO NOTHING
                RETURNING news_id;
            """
            for item in items:
                cur.execute(query, item)
                result = cur.fetchone()
                
                if result:
                    news_id = result[0]
                    cat_id, title, desc, dt, symbol, hash_key, is_test = item
                    
                    # Qdrant 저장 (통일된 페이로드 구조)
                    vector = self.embed_model.encode(f"passage: {desc}").tolist()
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=[PointStruct(
                            id=news_id,
                            vector=vector,
                            payload={
                                "category_id": cat_id,
                                "sentiment": 0.0,
                                "source_type": "news",
                                "symbol": symbol
                            }
                        )]
                    )
                    saved += 1
            conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            print(f"❌ DB 에러: {e}")
        finally:
            if conn: conn.close()
        return saved

    def collect_rss(self):
        categories = self._get_db_categories()
        total_saved = 0
        print(f"\n📡 [뉴스 수집 시작] ({datetime.now().strftime('%H:%M:%S')})")

        for cat in categories:
            symbol = cat['symbol']
            url = f"https://news.google.com/rss/search?q={symbol}+crypto+when:1d&hl=en-US&gl=US&ceid=US:en"
            try:
                feed = feedparser.parse(url)
                items = []
                for entry in feed.entries:
                    title = entry.title
                    raw_desc = getattr(entry, 'description', '') or getattr(entry, 'summary', '')
                    desc = re.sub('<[^<]+?>', '', raw_desc)[:800].strip()
                    desc = desc.replace('&nbsp;', ' ')
                    if not desc: desc = title
                    dt = datetime.now(timezone.utc)
                    if 'published' in entry:
                        try: dt = parser.parse(entry.published)
                        except: pass
                    hash_key = hashlib.md5(f"{title}_{symbol}_{dt.strftime('%Y%m%d%H')}".encode('utf-8')).hexdigest()
                    items.append((cat['id'], title, desc, dt, symbol, hash_key, True))
                
                count = self._save_to_db(items)
                if count > 0:
                    print(f"      ✅ [{symbol}] {count}건 저장")
                    total_saved += count
            except Exception as e:
                print(f"      ⚠️ Google {symbol} 에러: {e}")

        for source, url in self.static_feeds.items():
            try:
                feed = feedparser.parse(url, agent='Mozilla/5.0')
                if not feed.entries: continue
                items = []
                for entry in feed.entries:
                    title = entry.title
                    raw_desc = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                    desc = re.sub('<[^<]+?>', '', raw_desc)[:800].strip()
                    text_search = (title + " " + desc).upper()
                    dt = datetime.now(timezone.utc)
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                    for cat in categories:
                        if cat['symbol'] in text_search:
                            hash_key = hashlib.md5(f"{title}_{cat['symbol']}".encode()).hexdigest()
                            items.append((cat['id'], title, desc, dt, cat['symbol'], hash_key, True))
                count = self._save_to_db(items)
                if count > 0:
                    print(f"      ✅ [{source}] {count}건 저장")
                    total_saved += count
            except: continue
        print(f"✨ 전체 수집 완료. 총 {total_saved}건 저장.")

def job(): RssCollector().collect_rss()

if __name__ == "__main__":
    job()
    schedule.every(30).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)