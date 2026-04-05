import ccxt
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003734649641"

PAIRS = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT"]
TIMEFRAMES = ["15m","30m","1h","4h","1d"]

EMA_FAST = 20
EMA_SLOW = 50
LOOKBACK = 20

STATE_FILE = "last_signal.json"

TF_SECONDS = {
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400
}

def send_telegram(msg):
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print("Telegram error:", e)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_data(exchange, pair, tf):
    try:
        ohlcv = exchange.fetch_ohlcv(pair, tf, limit=200)
        return pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    except:
        return None


def main():

    exchange = ccxt.mexc({"enableRateLimit": True})
    state = load_state()
    signals = {}

    # ===== COLLECT SIGNALS =====
    for pair in PAIRS:
        for tf in TIMEFRAMES:

            df = fetch_data(exchange, pair, tf)
            if df is None or len(df) < 100:
                continue

            df["ema20"] = df["close"].ewm(span=EMA_FAST).mean()
            df["ema50"] = df["close"].ewm(span=EMA_SLOW).mean()

            prev2 = df.iloc[-3]
            prev1 = df.iloc[-2]

            candle_time = int(prev1["time"] / 1000)
            utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            swing_high = df["high"].iloc[-(LOOKBACK+2):-2].max()
            swing_low  = df["low"].iloc[-(LOOKBACK+2):-2].min()

            # EMA BUY
            if prev2.ema20 <= prev2.ema50 and prev1.ema20 > prev1.ema50:
                key = f"{pair}_EMA_BUY"
                signals.setdefault(key, {"pair":pair,"type":"EMA_BUY","price":prev1.close,"timeframes":[],"utc":utc,"candle":candle_time})
                signals[key]["timeframes"].append(tf)

            # EMA SELL
            elif prev2.ema20 >= prev2.ema50 and prev1.ema20 < prev1.ema50:
                key = f"{pair}_EMA_SELL"
                signals.setdefault(key, {"pair":pair,"type":"EMA_SELL","price":prev1.close,"timeframes":[],"utc":utc,"candle":candle_time})
                signals[key]["timeframes"].append(tf)

            # BREAKOUT BUY
            if prev2.close <= swing_high and prev1.close > swing_high:
                key = f"{pair}_BREAKOUT_BUY"
                signals.setdefault(key, {"pair":pair,"type":"BREAKOUT_BUY","price":prev1.close,"level":swing_high,"timeframes":[],"utc":utc,"candle":candle_time})
                signals[key]["timeframes"].append(tf)

            # BREAKOUT SELL
            elif prev2.close >= swing_low and prev1.close < swing_low:
                key = f"{pair}_BREAKOUT_SELL"
                signals.setdefault(key, {"pair":pair,"type":"BREAKOUT_SELL","price":prev1.close,"level":swing_low,"timeframes":[],"utc":utc,"candle":candle_time})
                signals[key]["timeframes"].append(tf)

    # ===== SEND SIGNALS =====
    now = int(time.time())

    for key, data in signals.items():

        tf_seconds = [TF_SECONDS.get(tf,300) for tf in data["timeframes"]]
        min_tf_sec = min(tf_seconds)

        # ✅ FIX 1: proper validity
        if now - data["candle"] > min_tf_sec * 2:
            continue

        # ✅ FIX 2: duplicate AFTER validity
        global_key = f"{data['pair']}_{data['type']}"
        if state.get(global_key) == data["candle"]:
            continue

        pair = data["pair"]
        price = data["price"]
        utc = data["utc"]
        tf_text = ", ".join(sorted(set(data["timeframes"])))

        if data["type"] == "EMA_BUY":
            msg = f"🟢 BUY EMA\n\n{pair}\nTF: {tf_text}\nPrice: {price:.2f}\nUTC: {utc}"

        elif data["type"] == "EMA_SELL":
            msg = f"🔴 SELL EMA\n\n{pair}\nTF: {tf_text}\nPrice: {price:.2f}\nUTC: {utc}"

        elif data["type"] == "BREAKOUT_BUY":
            msg = f"🚀 BREAKOUT BUY\n\n{pair}\nTF: {tf_text}\nLevel: {data['level']:.2f}\nPrice: {price:.2f}\nUTC: {utc}"

        else:
            msg = f"📉 BREAKDOWN SELL\n\n{pair}\nTF: {tf_text}\nLevel: {data['level']:.2f}\nPrice: {price:.2f}\nUTC: {utc}"

        send_telegram(msg)

        # ✅ save AFTER sending
        state[global_key] = data["candle"]

        time.sleep(1)

    save_state(state)


if __name__ == "__main__":
    main()
