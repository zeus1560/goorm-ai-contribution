import pandas as pd
import torch
from sqlalchemy import create_engine, text
from transformers import pipeline
from tqdm import tqdm
import sys
import re
import schedule
import time
from datetime import datetime
from qdrant_client import QdrantClient

# ==========================================
# 1. 설정 및 DB 연결 (Global)
# ==========================================
DB_USER = "postgres"      
DB_PASSWORD = "0000"  
DB_HOST = "localhost"          
DB_PORT = "15432"               
DB_NAME = "app"       

db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 엔진은 전역으로 한 번만 생성 (매번 연결하면 부하 발생)
try:
    engine = create_engine(db_url)
    print("✅ [Init] DB 연결 성공!")
except Exception as e:
    print(f"❌ [Init] DB 연결 실패: {e}")
    sys.exit(1)

qdrant = QdrantClient(url="http://localhost:6333")
print("✅ [Init] Qdrant 연결 성공!")

# MPS(Mac) / CUDA / CPU 설정
if torch.backends.mps.is_available():
    device = torch.device("mps")
    print("🍎 Apple MPS 가속을 사용합니다.")
elif torch.cuda.is_available():
    device = torch.device("cuda")
    print("🚀 NVIDIA GPU를 사용합니다.")
else:
    device = torch.device("cpu")
    print("🐢 CPU를 사용합니다.")

# ==========================================
# 2. 사전 및 규칙 정의
# ==========================================
SLANG_DICT = {
    "떡락": " HUGE CRASH ", "폭락": " PLUMMET ", "나락": " HELL DUMP ",
    "한강": " SUICIDE DEPRESSION ", "돔황챠": " RUN AWAY ", "돔황차": " RUN AWAY ",
    "탈출": " ESCAPE ", "손절": " PANIC SELL ", "설거지": " SCAM DUMP ",
    "흑우": " VICTIM ", "물렸": " TRAPPED LOSS ", "상폐": " DELISTING ",
    "스캠": " SCAM ", "망했": " RUINED ", "무섭다": " FEAR ", "공포": " FEAR ",
    "떨린다": " FEAR ", "drained": " HACKED ", "털렸다": " HACKED ", "해킹": " HACKED ",
    "떡상": " HUGE PUMP ", "불장": " BULL MARKET ", "투더문": " MOONING ",
    "가즈아": " TO THE MOON ", "존버": " HODL ", "홀딩": " HODL ",
    "졸업": " RETIRE RICH ", "익절": " TAKE PROFIT ", "반등": " REBOUND ",
    "말아올려": " PUMP UP ", "풀매수": " ALL IN BUY ", "영끌": " ALL IN BUY ",
    "롱": " LONG POSITION "
}

HARD_RULES = {
    "negative": [
        "상장폐지", "상폐", "해킹당함", "해킹 당함", "drained", "hacked", 
        "rug pull", "러그풀", "출금 중단", "입출금 중단", "구속", "체포"
    ],
    "positive": []
}

# ==========================================
# 3. 모델 로드 (최초 1회만 실행)
# ==========================================
print("⏳ 모델 로딩 중... (이 과정은 한 번만 실행됩니다)")
pipe_news = pipeline("text-classification", model="ProsusAI/finbert", device=device, truncation=True, max_length=512)
pipe_trans = pipeline("translation", model="Helsinki-NLP/opus-mt-ko-en", device=device, truncation=True, max_length=512)
pipe_crypto = pipeline("text-classification", model="ElKulako/cryptobert", device=device, truncation=True, max_length=512)
print("✅ 모델 로딩 완료!")

# ==========================================
# 4. 헬퍼 함수
# ==========================================
def apply_hard_rules(text):
    for kw in HARD_RULES["negative"]:
        if kw in text: return 0.99, "negative"
    for kw in HARD_RULES["positive"]:
        if kw in text: return 0.99, "positive"
    return None, None

def inject_slang(text):
    for slang, eng in SLANG_DICT.items():
        if slang in text: text = text.replace(slang, eng)
    return text

def has_korean(text):
    return bool(re.search("[가-힣]", text))

def save_to_db(table, id_col, data):
    if not data: return
    print(f"   💾 {len(data)}건 [{table}] 점수 저장 중...")
    
    # 트랜잭션을 짧게 가져가기 위해 개별 업데이트 혹은 작은 단위로 처리
    try:
        with engine.connect() as conn: # begin() 대신 connect() 사용
            for item in data:
                query = text(f"""
                    UPDATE {table}
                    SET sentiment_score = :score, sentiment_label = :label
                    WHERE {id_col} = :id
                """)
                conn.execute(query, {"score": item["score"], "label": item["label"], "id": item["id"]})
                
                # Qdrant 업데이트 (기존 코드 유지)
                collection_name = "news_collection" if "news" in table else "community_collection"
                qdrant.set_payload(
                    collection_name=collection_name,
                    payload={"sentiment": item["score"]},
                    points=[item["id"]]
                )
            conn.commit() # 마지막에 한 번에 커밋
        print("   ✅ Postgres & Qdrant 점수 동기화 완료!")
    except Exception as e:
        print(f"   ❌ 저장 실패: {e}")
        
# ==========================================
# 5. 메인 분석 함수
# ==========================================
def analyze_news():
    query = """
    SELECT news_id, title, COALESCE(description, '') as description
    FROM news_data
    WHERE sentiment_score IS NULL
    ORDER BY news_id DESC;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    if len(df) == 0:
        return # 조용히 리턴

    print(f"\n📰 [NEWS] {len(df)}건 신규 분석 시작...")
    df['full_text'] = df.apply(lambda row: f"{row['title']} {row['description']}".strip(), axis=1)
    
    updates = []
    batch_size = 32

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i : i + batch_size]
        texts = batch['full_text'].tolist()
        ids = batch['news_id'].tolist()
        
        try:
            results = pipe_news(texts)
            for doc_id, res in zip(ids, results):
                updates.append({
                    "id": int(doc_id),
                    "score": float(res['score']),
                    "label": str(res['label'])
                })
        except Exception as e:
            print(f"   ⚠️ 배치 처리 에러: {e}")
            continue

    if updates:
        save_to_db("news_data", "news_id", updates)

def analyze_community():
    query = """
    SELECT community_id, title, COALESCE(description, '') as description
    FROM community_data
    WHERE sentiment_score IS NULL
    ORDER BY community_id DESC;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    if len(df) == 0:
        return

    print(f"\n👽 [COMMUNITY] {len(df)}건 신규 분석 시작...")
    df['full_text'] = df.apply(lambda row: f"{row['title']} {row['description']}".strip(), axis=1)
    
    updates = []
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing"):
        doc_id = row['community_id']
        text_content = row['full_text']
        if not text_content: continue

        # 1. Hard Rule
        hr_score, hr_label = apply_hard_rules(text_content)
        if hr_label:
            updates.append({"id": doc_id, "score": hr_score, "label": hr_label})
            continue

        # 2. Slang Injection
        text_content = inject_slang(text_content)

        # 3. Translation
        final_text = text_content
        if has_korean(text_content):
            try:
                trans_res = pipe_trans(text_content[:512])
                final_text = trans_res[0]['translation_text']
            except: pass

        # 4. AI Analysis
        try:
            res = pipe_crypto(final_text[:512])[0]
            raw_label = res['label']
            if raw_label == 'Bullish': label = 'positive'
            elif raw_label == 'Bearish': label = 'negative'
            else: label = 'neutral'
            
            updates.append({
                "id": int(doc_id),
                "score": float(res['score']),
                "label": label
            })
        except: continue

    if updates:
        save_to_db("community_data", "community_id", updates)

# ==========================================
# 6. 스케줄러 Job 및 실행
# ==========================================
def job():
    print(f"\n[🔄 분석 사이클 시작] {datetime.now().strftime('%H:%M:%S')}")
    try:
        analyze_news()
        analyze_community()
        print(f"[✅ 사이클 종료] 대기 모드로 전환...")
    except Exception as e:
        print(f"[❌ 사이클 에러] {e}")

if __name__ == "__main__":
    print("🚀 감성 분석 에이전트 가동 (10분 주기)")
    print("   -> 메모리에 모델 적재 완료. 대기 중...")
    
    # 1. 실행 즉시 한 번 처리
    job()
    
    # 2. 10분마다 반복 스케줄링
    schedule.every(30).minutes.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)