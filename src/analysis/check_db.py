import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def check_db_status():
    try:
        # DB 연결
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"), 
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            connect_timeout=5,
            options="-c client_encoding=UTF8"
        )
        cur = conn.cursor()
        
        # 1. 전체 데이터 개수 확인
        cur.execute("SELECT count(*) FROM news_data;")
        total_count = cur.fetchone()[0]
        
        # 2. 비활성화된 데이터 개수 확인
        cur.execute("SELECT count(*) FROM news_data WHERE is_active = FALSE;")
        inactive_count = cur.fetchone()[0]
        
        print("📊 현재 DB 상태 점검 📊")
        print(f"전체 데이터 개수: {total_count}개")
        print(f"비활성화(is_active=FALSE) 데이터 개수: {inactive_count}개")
        print(f"✅ 현재 활성화된 데이터 개수: {total_count - inactive_count}개\n")

        # 3. 비활성화된 데이터 샘플 확인 (선택 사항)
        if inactive_count > 0:
            cur.execute("SELECT news_id, symbol FROM news_data WHERE is_active = FALSE LIMIT 3;")
            sample_data = cur.fetchall()
            print("💤 비활성화된 데이터 샘플 (news_id, symbol):")
            for row in sample_data:
                print(f" - ID: {row[0]}, Symbol: {row[1]}")
                
    except Exception as e:
        print(f"❌ DB 연결 또는 쿼리 실행 중 오류 발생: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    check_db_status()