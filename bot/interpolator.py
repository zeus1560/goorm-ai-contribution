# bot/interpolator.py
import random
from typing import Dict, List


class EMA:
    def __init__(self, alpha: float):
        self.alpha = alpha
        self.value = None

    def update(self, price: float) -> float:
        if self.value is None:
            self.value = price
        else:
            self.value = self.alpha * price + (1 - self.alpha) * self.value
        return self.value


class SmoothPriceInterpolator:
    """
    실시간 차트용 가격 보간기 (완성형)

    핵심 원칙
    1. clamp 기준은 raw vs raw
    2. chart price는 절대 clamp 기준으로 사용하지 않음
    3. 최초 값은 보간하지 않음
    """

    def __init__(
        self,
        alpha: float = 0.15,
        max_change: float = 0.003,   # 0.3%
        steps: int = 6
    ):
        self.alpha = alpha
        self.max_change = max_change
        self.steps = steps
        self.state: Dict[str, Dict] = {}

    def _clamp_raw(self, prev_raw: float, new_raw: float) -> float:
        diff = new_raw - prev_raw
        limit = prev_raw * self.max_change

        if abs(diff) > limit:
            return prev_raw + limit * (1 if diff > 0 else -1)
        return new_raw

    def smooth(self, coin: str, new_raw_price: float) -> List[float]:
        """
        :param coin: KRW-BTC
        :param new_raw_price: 거래소 원본 가격
        :return: 차트용 가격 리스트 (프레임 단위)
        """

        # 1️⃣ 최초 수신 → 그대로 1개만 반환
        if coin not in self.state:
            ema = EMA(self.alpha)
            ema.update(new_raw_price)

            self.state[coin] = {
                "last_raw": new_raw_price,
                "ema": ema
            }
            return [round(new_raw_price, 4)]

        state = self.state[coin]
        prev_raw = state["last_raw"]
        ema = state["ema"]

        # 2️⃣ raw 기준 clamp (가장 중요)
        clamped_raw = self._clamp_raw(prev_raw, new_raw_price)

        # 3️⃣ raw 기준 보간
        delta = (clamped_raw - prev_raw) / self.steps
        interpolated_raw = [
            prev_raw + delta * i
            for i in range(1, self.steps + 1)
        ]

        # 4️⃣ EMA + 미세 노이즈 (차트 자연스러움)
        result: List[float] = []
        for raw in interpolated_raw:
            smooth_price = ema.update(raw)

            noise = smooth_price * random.uniform(-0.00015, 0.00015)
            result.append(round(smooth_price + noise, 4))

        # 5️⃣ 상태 업데이트
        state["last_raw"] = clamped_raw

        return result
