import schedule
import time
from datetime import datetime
from dotenv import load_dotenv
from agent.generator import ReportGenerator

load_dotenv()

# 기존 DB 설정 및 타겟 코인 정보
DB_CONFIG = {
    "host": "localhost", "port": "15432",
    "database": "app", "user": "postgres", "password": "0000"
}

TARGET_COINS = [
    {"ticker": "KRW-BTC", "id": 223, "name": "비트코인", "symbol": "BTC"},
    {"ticker": "KRW-ETH", "id": 80, "name": "이더리움", "symbol": "ETH"},
    {"ticker": "KRW-SOL", "id": 198, "name": "솔라나",   "symbol": "SOL"},
    {"ticker": "KRW-XRP", "id": 148, "name": "리플",     "symbol": "XRP"}
]

def job():
    print(f"\n[🔄 RAG 분석 시스템 가동] {datetime.now()}")
    try:
        agent = ReportGenerator(DB_CONFIG, TARGET_COINS)
        agent.run_analysis()
    except Exception as e:
        print(f"🔥 치명적 에러: {e}")

if __name__ == "__main__":
    job() # 즉시 한 번 실행
    schedule.every(30).minutes.do(job) # 30분마다 반복 실행
    
    while True:
        schedule.run_pending()
        time.sleep(1)