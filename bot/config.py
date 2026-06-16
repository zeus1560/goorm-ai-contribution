import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    # 배포/로컬 환경에 맞춰 접속 정보를 수정해서 사용하세요!
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"), 
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5,
        options="-c client_encoding=UTF8"
    )

def sync_top_100_with_vip():
    # 💡 무조건 포함시킬 '근본/메이저 코인' 리스트
    VIP_COINS = ['BTC', 'ETH', 'XRP', 'SOL', 'ADA', 'DOGE', 'AVAX', 'DOT', 'LINK', 'BCH', 'SHIB']
    
    # 1. 업비트 전체 KRW 마켓 정보 가져오기
    url = "https://api.upbit.com/v1/market/all"
    res = requests.get(url)
    all_markets = res.json()
    krw_markets = [m for m in all_markets if m['market'].startswith('KRW-')]
    
    market_codes = [m['market'] for m in krw_markets]
    
    # DB에 집어넣을 전체 코인 심볼 리스트 (예: BTC, ETH)
    all_symbols = [m['market'].replace('KRW-', '') for m in krw_markets]
    
    # 2. 현재 시세를 가져와서 24시간 거래대금 순으로 정렬
    ticker_url = f"https://api.upbit.com/v1/ticker?markets={','.join(market_codes)}"
    tickers = requests.get(ticker_url).json()
    
    sorted_tickers = sorted(tickers, key=lambda x: x['acc_trade_price_24h'], reverse=True)

    # 3. VIP 코인을 먼저 담고, 남은 자리를 거래대금 상위 코인으로 채워 딱 100개 맞추기
    active_symbols = set(VIP_COINS)
    
    for t in sorted_tickers:
        if len(active_symbols) >= 100:
            break
            
        symbol = t['market'].replace('KRW-', '')
        active_symbols.add(symbol)

    # 4. DB 접속 및 INSERT / UPDATE 처리
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # ⭐ [추가된 핵심 로직] 1. DB에 없는 코인은 새로 추가, 이미 있으면 무시
        insert_query = """
            INSERT INTO category (symbol) 
            VALUES (%s) 
            ON CONFLICT (symbol) DO NOTHING;
        """
        for symbol in all_symbols:
            cur.execute(insert_query, (symbol,))

        # 2. DB에 있는 전체 코인 목록 가져오기
        cur.execute("SELECT symbol FROM category;")
        all_db_symbols = [row[0] for row in cur.fetchall()]

        # 3. 비활성화/활성화 대상 분류
        symbols_to_disable = [s for s in all_db_symbols if s not in active_symbols]
        symbols_to_enable = list(active_symbols)

        # 4. 상태 업데이트
        if symbols_to_disable:
            cur.execute(
                "UPDATE category SET is_active = FALSE WHERE symbol = ANY(%s);",
                (symbols_to_disable,)
            )
            
        if symbols_to_enable:
            cur.execute(
                "UPDATE category SET is_active = TRUE WHERE symbol = ANY(%s);",
                (symbols_to_enable,)
            )

        conn.commit()
        print(f"✅ DB 업데이트가 완벽하게 끝났습니다!")
        print(f"🆕 새로운 코인 추가(INSERT) 및 중복 검사 완료")
        print(f"👑 VIP 포함 상위 100개 세팅 완료")
        print(f"💤 100위 밖 {len(symbols_to_disable)}개 코인 꿀잠(비활성화) 처리 완료")

    except Exception as e:
        conn.rollback()
        print(f"❌ 오류 발생: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    sync_top_100_with_vip()