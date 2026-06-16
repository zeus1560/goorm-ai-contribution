import requests
import psycopg2
import jwt
import uuid
import hashlib
from urllib.parse import urlencode
from datetime import datetime
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------- [설정 영역] ----------------
ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY')
SECRET_KEY = os.getenv('UPBIT_SECRET_KEY')

DB_CONFIG = {
    "host": "localhost",
    "port": 15432,
    "user": "postgres",
    "password": "0000",
    "database": "app"
}

# 1. 상패 및 미수집 코인 3개(LTC, EOS, MATIC)를 제외한 13개 코인 리스트
TICKERS = [
    'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA', 'DOT', 
    'LINK', 'FIL', 'SHIB', 'ATOM', 'ALGO', 'TRX'
]

# 2. 데이터 분리 기준점 (뉴스 데이터와 동일하게 설정)
SPLIT_POINT = datetime.strptime('2026-01-20 00:57:16', '%Y-%m-%d %H:%M:%S')
START_DATE = datetime(2025, 10, 1) # 수집 시작 목표 시점
# --------------------------------------------

def get_auth_header(params=None):
    payload = {'access_key': ACCESS_KEY, 'nonce': str(uuid.uuid4())}
    if params:
        query_string = urlencode(params).encode()
        m = hashlib.sha512()
        m.update(query_string)
        payload['query_hash'] = m.hexdigest()
        payload['query_hash_alg'] = 'SHA512'
    return {"Authorization": f"Bearer {jwt.encode(payload, SECRET_KEY)}"}

def fetch_and_store_prices():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    for ticker in TICKERS:
        print(f"\n>>> {ticker} 데이터 수집 및 자동 분리 시작...")
        current_to = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        while True:
            params = {'market': f'KRW-{ticker}', 'to': current_to, 'count': 200}
            url = "https://api.upbit.com/v1/candles/minutes/60"
            headers = get_auth_header(params)
            
            try:
                response = requests.get(url, params=params, headers=headers)
                res_data = response.json()
                
                if not res_data or 'error' in res_data: break
                
                for candle in res_data:
                    kst_time_str = candle['candle_date_time_kst'].replace('T', ' ')
                    kst_time_dt = datetime.strptime(kst_time_str, '%Y-%m-%d %H:%M:%S')
                    
                    # [핵심] 수집 시점에 바로 테스트 데이터 여부 판단
                    is_test_val = kst_time_dt >= SPLIT_POINT
                    
                    cur.execute("""
                        INSERT INTO market_price (ticker, trade_price, trade_volume, trade_time, is_test)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, trade_time) DO NOTHING
                    """, (
                        ticker, 
                        candle['trade_price'], 
                        candle['candle_acc_trade_volume'], 
                        kst_time_str,
                        is_test_val
                    ))
                
                conn.commit()
                last_candle_time = datetime.strptime(res_data[-1]['candle_date_time_kst'], '%Y-%m-%dT%H:%M:%S')
                current_to = res_data[-1]['candle_date_time_kst']
                
                print(f"[{ticker}] {current_to} 저장 중... (테스트여부: {is_test_val})")
                
                if last_candle_time < START_DATE: break
                time.sleep(0.1) # API 부하 방지
                
            except Exception as e:
                print(f"Error during {ticker}: {e}")
                break

    print("\n✅ 모든 데이터 수집 및 'is_test' 분류가 완료되었습니다!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    fetch_and_store_prices()