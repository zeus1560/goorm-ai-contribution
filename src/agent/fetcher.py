import psycopg2

class ContextFetcher:
    def __init__(self, db_config):
        self.db_params = db_config

    def get_past_original_text(self, search_results):
        if not search_results:
            return ""

        news_ids = [r['id'] for r in search_results if r['source'] == "news"]
        comm_ids = [r['id'] for r in search_results if r['source'] == "community"]
        
        texts = []
        conn = psycopg2.connect(**self.db_params)
        cur = conn.cursor()

        # news_id를 사용하여 실제 본문 조회
        if news_ids:
            cur.execute("SELECT description FROM news_data WHERE news_id IN %s", (tuple(news_ids),))
            texts.extend([f"[과거 뉴스 참고]: {row[0][:300]}..." for row in cur.fetchall()])
            
        # community_id를 사용하여 실제 본문 조회
        if comm_ids:
            cur.execute("SELECT description FROM community_data WHERE community_id IN %s", (tuple(comm_ids),))
            texts.extend([f"[과거 커뮤니티 참고]: {row[0][:300]}..." for row in cur.fetchall()])

        cur.close()
        conn.close()
        return "\n\n".join(texts)