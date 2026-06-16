import feedparser
import hashlib
import psycopg2
import time
import schedule
import requests
import random
import logging
import sys
import torch
import os
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from datetime import datetime, timezone
from time import mktime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('reddit_collector.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ==========================================================
# 🚀 1. 전역 설정 및 모델 초기화 (프로그램 시작 시 딱 한 번만 수행)
# ==========================================================
print("💡 시스템 초기화 중: 임베딩 모델을 로드합니다...")
device = "mps" if torch.backends.mps.is_available() else "cpu"
# 모델 로드 시 허깅페이스 서버 접속 에러 방지를 위해 전역에서 한 번만 로드
try:
    shared_model = SentenceTransformer('intfloat/multilingual-e5-small', device=device)
    print("✅ 모델 로드 완료!")
except Exception as e:
    logging.error(f"❌ 모델 로드 실패: {e}")
    sys.exit(1) # 모델 로드 실패 시 시작 불가

class CommunityCollector:
    def __init__(self, model):
        self.db_params = {
            "host": "localhost", "port": "15432",
            "database": "app", "user": "postgres", "password": "0000"
        }
        
        self.embed_model = model # 주입받은 모델 사용
        self.qdrant_client = QdrantClient(url="http://localhost:6333")
        self.collection_name = "community_collection"

        self.subreddit_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp",
            "ADA": "cardano", "DOGE": "dogecoin", "DOT": "polkadot", "LINK": "chainlink"
        }
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _get_category_mapping(self):
        """DB에서 symbol과 category_id 매핑 정보 가져오기"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()
            cur.execute("SELECT symbol, category_id FROM public.category")
            rows = cur.fetchall()
            conn.close()
            return {r[0].upper(): r[1] for r in rows}
        except Exception as e:
            logging.error(f"⚠️ 카테고리 매핑 로드 실패: {e}")
            return {}

    def _save_to_db(self, items, ticker, sort_type, cat_id):
        if not items: return 0
        conn = None
        saved_count = 0
        try:
            # search_path=public 설정을 추가하여 테이블 찾기 에러 방지
            conn = psycopg2.connect(**self.db_params, options="-c search_path=public")
            cur = conn.cursor()
            
            query = """
                INSERT INTO community_data
                (symbol, title, description, published_at, hash_key, platform, ups, is_test, category_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hash_key) DO UPDATE SET ups = EXCLUDED.ups
                RETURNING community_id;
            """
            
            for item in items:
                db_item = item + (cat_id,)
                cur.execute(query, db_item)
                result = cur.fetchone()
                
                if result:
                    comm_id = result[0]
                    symbol, title, description, dt, hash_key, platform, ups, is_test = item
                    
                    # 벡터화 및 Qdrant 저장
                    vector = self.embed_model.encode(f"passage: {description}").tolist()
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=[PointStruct(
                            id=comm_id,
                            vector=vector,
                            payload={
                                "category_id": cat_id,
                                "sentiment": 0.0,
                                "source_type": "community",
                                "symbol": symbol
                            }
                        )]
                    )
                    saved_count += 1
            
            conn.commit()
            if saved_count > 0: 
                logging.info(f"💾 [{ticker}-{sort_type}] {saved_count}건 저장 완료")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"❌ DB 저장 에러: {e}")
        finally:
            if conn: conn.close()
        return saved_count

    def collect_reddit(self):
        logging.info("👽 [Reddit-RSS] 수집 사이클 시작")
        cat_map = self._get_category_mapping()
        
        for ticker, subreddit in self.subreddit_map.items():
            cat_id = cat_map.get(ticker.upper())
            if not cat_id: continue

            for sort_type in ["new", "hot"]:
                url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.rss"
                try:
                    headers = {'User-Agent': random.choice(self.user_agents)}
                    resp = requests.get(url, headers=headers, timeout=15)
                    if resp.status_code != 200: continue
                    
                    feed = feedparser.parse(resp.content)
                    items_to_save = []
                    for entry in feed.entries:
                        dt = datetime.now(timezone.utc)
                        if hasattr(entry, 'published_parsed'):
                            dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                        
                        title = entry.title
                        description = getattr(entry, 'summary', '')
                        hash_key = hashlib.md5(f"{title}_{dt}".encode('utf-8')).hexdigest()
                        items_to_save.append((ticker, title, description, dt, hash_key, 'reddit', 0, True))

                    self._save_to_db(items_to_save, ticker, sort_type, cat_id)
                    time.sleep(random.randint(2, 5)) # 사이클 내 딜레이
                except Exception as e:
                    logging.error(f"⚠️ 네트워크 에러 [{ticker}]: {e}")
        logging.info("✨ 수집 사이클 종료.")

# ==========================================================
# 🚀 2. 실행부: 스케줄러 설정
# ==========================================================
collector = CommunityCollector(shared_model) # 객체 하나만 생성하여 재사용

def job():
    try:
        collector.collect_reddit()
    except Exception as e:
        logging.error(f"🚨 작업 중 치명적 에러: {e}")

if __name__ == "__main__":
    # 처음 실행
    job()
    
    # 30분마다 반복
    schedule.every(30).minutes.do(job)
    
    print("⏰ 스케줄러 가동 중... (30분 간격)")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            # 네트워크가 끊겨도 스케줄러 자체가 죽지 않도록 방어
            logging.error(f"⚠️ 스케줄러 내부 오류 (다음 주기 재시도): {e}")
        time.sleep(1)