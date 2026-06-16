import time
import requests
from threading import Thread, Lock, Event

from bot.config import (
    SPRING_ORDER_URL,
    SECRET_TOKEN,
    THREADS,
    ORDER_INTERVAL,
    CATEGORY_MAP
)
from bot.order import create_order
from bot.price import fetch_upbit_price
from bot.interpolator import SmoothPriceInterpolator


interpolator = SmoothPriceInterpolator(alpha=0.15)

print_lock = Lock()
stop_event = Event()

success = 0
fail = 0


def send_order(order: dict):
    global success, fail

    try:
        res = requests.post(
            SPRING_ORDER_URL,
            json=order,
            headers={
                "X-Internal-Token": SECRET_TOKEN,
                "Content-Type": "application/json"
            },
            timeout=10
        )

        with print_lock:
            if res.status_code == 200:
                success += 1
                print(
                    f"✅ [BOT] {order['_coin']} "
                    f"{order['orderType']} "
                    f"{order['orderCount']} @ {order['orderPrice']}"
                )
            else:
                fail += 1
                print(f"❌ FAIL {res.status_code}")
                print(f"   응답: {res.text}")

    except Exception as e:
        with print_lock:
            fail += 1
            print(f"💥 요청 예외: {e}")


def bot_worker():
    while not stop_event.is_set():
        order = create_order()

        if order is None:
            time.sleep(0.1)
            continue

        send_order(order)
        time.sleep(ORDER_INTERVAL)

def worker_loop():
    coins = list(CATEGORY_MAP.keys())

    while True:
        prices = fetch_upbit_price(coins)

        for coin, upbit_price in prices.items():
            smooth_prices = interpolator.smooth(coin, upbit_price)

            for price in smooth_prices:
                order = create_order(coin, price)
                send_order(order)

                # 차트 프레임 분할용 sleep
                time.sleep(ORDER_INTERVAL / len(smooth_prices))


def start():
    print("\n🚀 BOT 주문 시뮬레이션 시작 (무한 실행)")
    start_time = time.time()

    threads = []
    for i in range(THREADS):
        t = Thread(target=bot_worker, name=f"BOT-{i}")
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 종료 신호 감지")
        stop_event.set()

    for t in threads:
        t.join()

    elapsed = time.time() - start_time
    total = success + fail

    print("\n==============================")
    print(f"총 주문 수 : {total}")
    print(f"성공      : {success}")
    print(f"실패      : {fail}")
    print(f"평균 TPS  : {total / elapsed:.2f}")
    print("==============================")
