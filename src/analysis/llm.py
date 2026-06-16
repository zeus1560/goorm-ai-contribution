import os
import json
import schedule
import time
import requests
import re
import pandas as pd
import psycopg2
from datetime import datetime
from langchain_cohere import ChatCohere
from dotenv import load_dotenv

load_dotenv()

COHERE_API_KEY = os.getenv('COHERE_API_KEY')

DB_CONFIG = {
    "host": "localhost", "port": "15432",
    "database": "app", "user": "postgres", "password": "0000"
}

TARGET_COINS = [
    {"ticker": "KRW-BTC", "id": 1, "name": "비트코인", "symbol": "BTC"},
    {"ticker": "KRW-ETH", "id": 2, "name": "이더리움", "symbol": "ETH"},
    {"ticker": "KRW-SOL", "id": 3, "name": "솔라나",   "symbol": "SOL"},
    {"ticker": "KRW-XRP", "id": 4, "name": "리플",     "symbol": "XRP"}
]

def extract_json(text):
    try:
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match: return json.loads(match.group(1))
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match: return json.loads(match.group(1))
        return json.loads(text)
    except:
        return None

def fetch_coin_specific_data(symbol):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    cur.execute("SELECT AVG(sentiment_score) FROM news_data WHERE symbol = %s", (symbol,))
    row = cur.fetchone()
    hist_news_avg = row[0] if row and row[0] else 0.5
    
    cur.execute("SELECT AVG(sentiment_score) FROM community_data WHERE symbol = %s", (symbol,))
    row = cur.fetchone()
    hist_comm_avg = row[0] if row and row[0] else 0.5
    
    cur.execute("SELECT AVG(sentiment_score) FROM news_data WHERE symbol = %s AND published_at >= NOW() - INTERVAL '24 HOURS'", (symbol,))
    row = cur.fetchone()
    curr_news_avg = row[0] if row and row[0] else hist_news_avg

    cur.execute("SELECT AVG(sentiment_score) FROM community_data WHERE symbol = %s AND published_at >= NOW() - INTERVAL '24 HOURS'", (symbol,))
    row = cur.fetchone()
    curr_comm_avg = row[0] if row and row[0] else hist_comm_avg

    cur.execute("SELECT title FROM news_data WHERE symbol = %s ORDER BY published_at DESC LIMIT 5", (symbol,))
    news_rows = cur.fetchall()
    
    cur.execute("SELECT title FROM community_data WHERE symbol = %s ORDER BY published_at DESC LIMIT 5", (symbol,))
    comm_rows = cur.fetchall()

    cur.close()
    conn.close()
    
    context_summary = f"[평균] 뉴스({hist_news_avg:.2f}), 커뮤니티({hist_comm_avg:.2f}) / [현재] 뉴스({curr_news_avg:.2f}), 커뮤니티({curr_comm_avg:.2f})"
    return context_summary, news_rows, comm_rows, curr_news_avg, curr_comm_avg

def get_rsi_analysis(ticker):
    try:
        url = "https://api.upbit.com/v1/candles/days"
        res = requests.get(url, params={"market": ticker, "count": 200})
        df = pd.DataFrame(res.json()).iloc[::-1]
        df['close'] = df['trade_price']
        delta = df['close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1], f"RSI: {rsi.iloc[-1]:.1f}"
    except:
        return 50.0, "RSI 계산 실패"

def save_report_to_db(cat_id, report_json, rsi_val, news_avg, comm_avg):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        query = """
            INSERT INTO sentiment_result (
                category_id, total_score, total_label, 
                news_result, community_result,
                summary, full_report, rsi, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (category_id) DO UPDATE SET
                total_score = EXCLUDED.total_score,
                total_label = EXCLUDED.total_label,
                news_result = EXCLUDED.news_result,
                community_result = EXCLUDED.community_result,
                summary = EXCLUDED.summary,
                full_report = EXCLUDED.full_report,
                rsi = EXCLUDED.rsi,
                created_at = NOW();
        """
        cur.execute(query, (
            cat_id,
            report_json.get("confidence_score", 50),
            report_json.get("signal", "HOLD"),
            float(news_avg),
            float(comm_avg),
            report_json.get("primary_reason", ""),
            report_json.get("full_report", ""),
            float(rsi_val)
        ))
        conn.commit()
        print(f"✅ ID {cat_id} 저장 완료")
    except Exception as e:
        print(f"❌ DB 저장 실패 (ID {cat_id}): {e}")
    finally:
        if conn: conn.close()

def run_full_analysis():
    chat = ChatCohere(model="command-r-plus-08-2024", temperature=0.3)
    
    for coin in TARGET_COINS:
        try:
            print(f">>> [{coin['name']}] 분석 시작...")
            context, news, comm, n_avg, c_avg = fetch_coin_specific_data(coin['symbol'])
            rsi_val, rsi_msg = get_rsi_analysis(coin['ticker'])
            
            news_str = "\n".join([f"- {r[0]}" for r in news]) if news else "(뉴스 없음)"
            comm_str = "\n".join([f"- {r[0]}" for r in comm]) if comm else "(글 없음)"

            # [수정됨] 프롬프트에 마크다운 출력 형식 및 JSON 줄바꿈 규칙 강제 추가
            prompt = f"""
            [분석 대상: {coin['name']}]
            {context}
            [뉴스]
            {news_str}
            [커뮤니티]
            {comm_str}
            [지표]
            {rsi_msg}
            
            투자 리포트를 작성하세요. 
            **반드시 아래 JSON 형식으로만 출력하세요.** 잡담 금지.
            (주의: JSON 문자열 내의 줄바꿈은 반드시 \\n 으로 이스케이프 처리하세요.)

            {{
                "signal": "BUY/SELL/HOLD",
                "confidence_score": 0~100 중 숫자 하나,
                "primary_reason": "한 줄 요약",
                "full_report": "### 📊 시장 분석\\n(시장 상황 1~2줄 요약)\\n\\n### 📰 주요 뉴스 및 커뮤니티 동향\\n- (동향 요약 1)\\n- (동향 요약 2)\\n\\n### 💡 종합 투자 의견\\n(RSI 및 감성 점수를 바탕으로 한 최종 결론)"
            }}
            """
            
            resp = chat.invoke(prompt)
            result_json = extract_json(resp.content)
            
            if result_json:
                save_report_to_db(coin['id'], result_json, rsi_val, n_avg, c_avg)
            else:
                print(f"❌ {coin['name']} JSON 파싱 실패 (내용이 이상함)")
                
        except Exception as e:
            print(f"❌ {coin['name']} 에러: {e}")

def job():
    print(f"\n[🔄 시스템 시작] {datetime.now()}")
    run_full_analysis()

if __name__ == "__main__":
    job()
    schedule.every(30).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)