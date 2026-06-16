import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": "15432",
    "database": "app", "user": "postgres", "password": "0000"
}

def confirm():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # 쿼리를 안전하게 전체 조회로 바꿨습니다.
    cur.execute("SELECT * FROM sentiment_result ORDER BY created_at DESC LIMIT 5;")
    rows = cur.fetchall()
    
    # 컬럼 이름 가져오기
    colnames = [desc[0] for desc in cur.description]
    
    print(f"📊 [조회 결과] 총 {len(rows)}개의 최신 리포트를 찾았습니다.")
    print("-" * 50)
    for row in rows:
        # 데이터를 딕셔너리 형태로 출력해서 보기 편하게 만듭니다.
        result = dict(zip(colnames, row))
        print(f"📍 카테고리 ID: {result.get('category_id')} | 결과: {result.get('signal')} | 시간: {result.get('created_at')}")
    print("-" * 50)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    confirm()