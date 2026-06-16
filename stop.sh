#!/bin/bash
GREEN='\033[0;32m'
NC='\033[0m'

echo "🛑 시스템을 안전하게 종료합니다..."
pkill -f news_collector.py
pkill -f community_aggregator.py
pkill -f sentiment_analyzer.py
pkill -f main.py
sleep 1

echo -e "${GREEN}✅ 모든 AI 에이전트가 성공적으로 종료되었습니다.${NC}"