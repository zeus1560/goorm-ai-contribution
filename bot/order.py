# bot/order.py
import random
from typing import Optional, Dict
from bot.config import COINS, CATEGORY_MAP, BOT_ID
from bot.price import random_price

TOP_7_COINS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA', 'DOT']

COIN_WEIGHTS = []
top_coins_in_db = [c for c in COINS if c in TOP_7_COINS]
other_coins = [c for c in COINS if c not in TOP_7_COINS]

top_weight = 0.5 / len(top_coins_in_db) if top_coins_in_db else 0

other_weight = 0.5 / len(other_coins) if other_coins else 0

for c in COINS:
    if c in TOP_7_COINS:
        COIN_WEIGHTS.append(top_weight)
    else:
        COIN_WEIGHTS.append(other_weight)

def create_order() -> Optional[Dict]:

    coin = random.choices(COINS, weights=COIN_WEIGHTS, k=1)[0]
    
    price = random_price(coin)

    if price is None:
        return None

    order_type = random.choice(["BUY", "SELL"])

    return {
        "botId": BOT_ID,
        "categoryId": CATEGORY_MAP[coin],
        "orderPrice": price,
        "orderCount": round(random.uniform(0.1, 3), 4),
        "orderType": order_type,
        "_coin": coin
    }