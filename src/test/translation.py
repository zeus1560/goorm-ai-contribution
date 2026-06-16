import psycopg2
import pandas as pd

# DB 접속 정보
DB_CONFIG = {
    "host": "localhost",
    "port": "15432",
    "database": "app",
    "user": "postgres",
    "password": "0000"
}

def check_sentiment_range():
    conn = psycopg2.connect(**DB_CONFIG)
    
    # 통계 쿼리: 최솟값, 최댓값, 평균, 데이터 개수 확인
    query = """
        SELECT 
            MIN(sentiment_score) as min_score,
            MAX(sentiment_score) as max_score,
            AVG(sentiment_score) as avg_score,
            COUNT(*) as total_count
        FROM news_data
        WHERE sentiment_score IS NOT NULL;
    """
    
    # 샘플 데이터 5개 확인 (실제 값 눈으로 보기)
    sample_query = "SELECT title, sentiment_score FROM news_data WHERE sentiment_score IS NOT NULL LIMIT 5;"

    df_stats = pd.read_sql(query, conn)
    df_samples = pd.read_sql(sample_query, conn)
    
    conn.close()

    print("\n=== 📊 감성 점수 통계 ===")
    print(df_stats)
    print("\n=== 🔍 실제 데이터 샘플 ===")
    print(df_samples)

    # 범위 판단 로직
    min_val = df_stats.iloc[0]['min_score']
    max_val = df_stats.iloc[0]['max_score']

    print("\n=== 💡 결론 ===")
    if min_val < 0:
        print(f"✅ 확인됨: 점수 범위는 [-1 ~ 1] 입니다.")
        print("   - 음수(-): 부정 / 0: 중립 / 양수(+): 긍정")
        print("   - 추천 기준점: 0.5 ~ 0.7 이상")
    else:
        print(f"✅ 확인됨: 점수 범위는 [0 ~ 1] 입니다.")
        print("   - 0에 가까움: 부정? (모델에 따라 다름) / 1에 가까움: 긍정")
        print("   - 0.5가 중립일 가능성이 높음")

if __name__ == "__main__":
    check_sentiment_range()