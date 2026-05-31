import ccxt
import pandas as pd
import requests
import os
import time
import json
import subprocess
from datetime import datetime

# ================= TELEGRAM =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003734649641"
# ===========================================

PAIRS = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","GOLD(PAXG)/USDT"]
TIMEFRAMES = ["15m","30m","1h","4h","1d"]

EMA_FAST = 20
EMA_SLOW = 50
LOOKBACK = 20

TF_SECONDS = {
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400
}

# ================= FILE STORAGE =================
SIGNAL_FILE = "sent_signals.json"

def load_sent_signals():
    if os.path.exists(SIGNAL_FILE):
        try:
            with open(SIGNAL_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sent_signals(data):
    with open(SIGNAL_FILE, "w") as f:
        json.dump(data, f)

# ================= GITHUB PUSH =================
def push_to_github():
    try:
        subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
        subprocess.run(["git", "config", "--global", "user.name", "crypto-bot"])

        subprocess.run(["git", "add", SIGNAL_FILE])
        subprocess.run(["git", "commit", "-m", "update signals"], check=False)
        subprocess.run(["git", "push"], check=False)

    except Exception as e:
        print("Git push error:", e)

# ================= TELEGRAM =================
def send_telegram(msg):
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# ================= DATA =================
def fetch_data(exchange, pair, tf):
    try:
        ohlcv = exchange.fetch_ohlcv(pair, tf, limit=200)
        return pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    except:
        return None

# ================= MAIN =================
def main():

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing")

    exchange = ccxt.mexc({"enableRateLimit": True})
    signals = {}

    sent_history = load_sent_signals()

    # ================= BOT START =================
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send_telegram(
            "🤖 <b>Crypto Signals Bot Started</b>\n"
            "📡 Exchange: MEXC\n"
            "⚙️ Strategy: EMA 20/50 + Breakout\n"
            "🚀 Status: Manual Start"
        )

    # ================= SIGNAL COLLECTION =================
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
                signals.setdefault(key, {
                    "pair": pair,
                    "type": "EMA_BUY",
                    "price": prev1.close,
                    "timeframes": [],
                    "utc": utc,
                    "candle": candle_time
                })
                signals[key]["timeframes"].append(tf)

            # EMA SELL
            elif prev2.ema20 >= prev2.ema50 and prev1.ema20 < prev1.ema50:
                key = f"{pair}_EMA_SELL"
                signals.setdefault(key, {
                    "pair": pair,
                    "type": "EMA_SELL",
                    "price": prev1.close,
                    "timeframes": [],
                    "utc": utc,
                    "candle": candle_time
                })
                signals[key]["timeframes"].append(tf)

            # BREAKOUT BUY
            if prev2.close <= swing_high and prev1.close > swing_high:
                key = f"{pair}_BREAKOUT_BUY"
                signals.setdefault(key, {
                    "pair": pair,
                    "type": "BREAKOUT_BUY",
                    "price": prev1.close,
                    "level": swing_high,
                    "timeframes": [],
                    "utc": utc,
                    "candle": candle_time
                })
                signals[key]["timeframes"].append(tf)

            # BREAKOUT SELL
            elif prev2.close >= swing_low and prev1.close < swing_low:
                key = f"{pair}_BREAKOUT_SELL"
                signals.setdefault(key, {
                    "pair": pair,
                    "type": "BREAKOUT_SELL",
                    "price": prev1.close,
                    "level": swing_low,
                    "timeframes": [],
                    "utc": utc,
                    "candle": candle_time
                })
                signals[key]["timeframes"].append(tf)

    # ================= SEND SIGNALS =================
    now = int(time.time())

    for key, data in signals.items():

        tf_seconds = [TF_SECONDS.get(tf,300) for tf in data["timeframes"]]
        min_tf_sec = min(tf_seconds)

        # ✅ Candle close check
        if now < data["candle"] + min_tf_sec + 5:
            continue

        # ✅ Validity window
        if now - data["candle"] > min_tf_sec * 2:
            continue

        pair = data["pair"]
        signal_type = data["type"]
        candle_time = str(data["candle"])

        # ================= 1D CONTROL =================
        if "1d" in data["timeframes"]:
            day_key = f"{pair}_{signal_type}_1d"

            if day_key in sent_history:
                continue

            if now < data["candle"] + 86400:
                continue

            sent_history[day_key] = candle_time

        # ================= OTHER TF CONTROL =================
        unique_id = f"{pair}_{signal_type}_{candle_time}"
        if unique_id in sent_history:
            continue

        sent_history[unique_id] = candle_time

        price = data["price"]
        utc = data["utc"]
        tf_text = ", ".join(sorted(set(data["timeframes"])))

        if data["type"] == "EMA_BUY":
            msg = (
                f"🟢 <b>BUY | EMA 20 > EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ TF: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
            )

        elif data["type"] == "EMA_SELL":
            msg = (
                f"🔴 <b>SELL | EMA 20 < EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ TF: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
            )

        elif data["type"] == "BREAKOUT_BUY":
            msg = (
                f"🚀 <b>BULLISH BREAKOUT</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ TF: {tf_text}\n"
                f"📈 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
            )

        else:
            msg = (
                f"📉 <b>BEARISH BREAKDOWN</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ TF: {tf_text}\n"
                f"📉 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
            )

        send_telegram(msg)

        # ✅ Save + push to GitHub (THIS IS THE ONLY NEW ADDITION)
        save_sent_signals(sent_history)
        push_to_github()

        time.sleep(1)

if __name__ == "__main__":
    main()
