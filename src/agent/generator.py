import os
import json
import re
import requests
import pandas as pd
import psycopg2
from langchain_cohere import ChatCohere
from .searcher import QdrantSearcher
from .fetcher import ContextFetcher

class ReportGenerator:
    def __init__(self, db_config, target_coins):
        self.db_config = db_config
        self.target_coins = target_coins
        self.searcher = QdrantSearcher()
        self.fetcher = ContextFetcher(db_config)
        
        self.chat = ChatCohere(
            model="command-r-plus-08-2024", 
            temperature=0.3,
            cohere_api_key=os.getenv('COHERE_API_KEY') 
        )

    def extract_json(self, text):
        try:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            json_str = match.group(1) if match else text
            match_fallback = re.search(r"(\{.*\})", json_str, re.DOTALL)
            if match_fallback:
                json_str = match_fallback.group(1)
            return json.loads(json_str, strict=False)
        except Exception as e:
            print(f"JSON 파싱 에러: {e}")
            return None

    def get_rsi_analysis(self, ticker):
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
        except: return 50.0, "RSI 계산 실패"

    def fetch_current_data(self, symbol):
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("SELECT title FROM news_data WHERE symbol = %s ORDER BY published_at DESC LIMIT 5", (symbol,))
        news = "\n".join([f"- {r[0]}" for r in cur.fetchall()])
        cur.close()
        conn.close()
        return news

    def save_report(self, cat_id, report_json, rsi_val, news_score, comm_score): # 인자 추가
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        query = """
            INSERT INTO sentiment_result 
            (category_id, total_score, total_label, summary, full_report, rsi, news_result, community_result, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (category_id) DO UPDATE SET
                total_score = EXCLUDED.total_score, 
                total_label = EXCLUDED.total_label,
                summary = EXCLUDED.summary, 
                full_report = EXCLUDED.full_report, 
                rsi = EXCLUDED.rsi,
                news_result = EXCLUDED.news_result,
                community_result = EXCLUDED.community_result,
                created_at = NOW();
        """
        cur.execute(query, (
            cat_id, 
            report_json.get("confidence_score", 50), 
            report_json.get("signal", "HOLD"),
            report_json.get("primary_reason", ""), 
            report_json.get("full_report", ""), 
            float(rsi_val),
            float(news_score), # 👈 뉴스 점수 추가
            float(comm_score)  # 👈 커뮤니티 점수 추가
        ))
        conn.commit()
        cur.close()
        conn.close()

    def get_avg_scores(self, symbol):
        """DB에서 해당 코인의 최근 뉴스/커뮤니티 평균 점수를 가져옵니다."""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        # 뉴스 평균 (최근 24시간 혹은 최근 20건 등)
        cur.execute("SELECT AVG(sentiment_score) FROM news_data WHERE symbol = %s AND sentiment_score IS NOT NULL", (symbol,))
        news_avg = cur.fetchone()[0] or 0.5
        
        # 커뮤니티 평균
        cur.execute("SELECT AVG(sentiment_score) FROM community_data WHERE symbol = %s AND sentiment_score IS NOT NULL", (symbol,))
        comm_avg = cur.fetchone()[0] or 0.5
        
        cur.close()
        conn.close()
        return news_avg, comm_avg

    # 👇 [주의] 이 함수가 누락되면 아까와 같은 에러가 발생합니다!
    def run_analysis(self):
        for coin in self.target_coins:
            print(f">>> [{coin['name']}] RAG 분석 시작...")
            current_news = self.fetch_current_data(coin['symbol'])
            rsi_val, rsi_msg = self.get_rsi_analysis(coin['ticker'])
            
            news_score, comm_score = self.get_avg_scores(coin['symbol'])

            search_results = self.searcher.search_similar_contexts(current_news, coin['id'])
            past_context = self.fetcher.get_past_original_text(search_results)
            
            prompt = f"""
            [대상: {coin['name']}]
            [현재 뉴스]: {current_news}
            [지표]: {rsi_msg}
            [과거 유사 사례]: {past_context if past_context else "기록 없음"}
            
            당신은 데이터 분석 API 서버입니다. 
            위 데이터를 바탕으로 투자 리포트를 작성하되, **반드시 아래의 순수 JSON 형식으로만** 응답하세요.
            {{
                "signal": "BUY",
                "confidence_score": 60,
                "primary_reason": "RSI 지표와 긍정적 뉴스 결합",
                "full_report": "마크다운 형식의 상세 리포트 내용"
            }}
            """
            
            resp = self.chat.invoke(prompt)
            result_json = self.extract_json(resp.content)
            
            if result_json:
                self.save_report(coin['id'], result_json, rsi_val, news_score, comm_score)
                print(f"✅ {coin['name']} 리포트 저장 완료 (ID: {coin['id']})")
            else:
                print(f"❌ {coin['name']} 리포트 파싱 실패")