import ccxt
import pandas as pd
import requests
import json
import os
from datetime import datetime

# ================= TELEGRAM =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003734649641"
# ===========================================

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]

EMA_FAST = 20
EMA_SLOW = 50
LOOKBACK = 20
STATE_FILE = "last_signal.json"


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
        df = pd.DataFrame(
            ohlcv,
            columns=["time", "open", "high", "low", "close", "volume"]
        )
        return df
    except Exception as e:
        print(f"Fetch error {pair} {tf}: {e}")
        return None


def main():

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in GitHub Secrets")

    exchange = ccxt.mexc({
    "enableRateLimit": True
    })

    state = load_state()

    # BOT START MESSAGE (manual run only)
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send_telegram(
            "🤖 <b>Crypto Signals Bot Started</b>\n"
            "📡 Exchange: Binance\n"
            "⚙️ Strategy: EMA 20/50 + Breakout\n"
            "🚀 Status: Manual Start"
        )

    for pair in PAIRS:
        for tf in TIMEFRAMES:

            try:

                df = fetch_data(exchange, pair, tf)

                if df is None:
                    continue

                df["ema20"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
                df["ema50"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

                prev = df.iloc[-2]
                curr = df.iloc[-1]

                swing_high = df["high"].iloc[-(LOOKBACK + 1):-1].max()
                swing_low = df["low"].iloc[-(LOOKBACK + 1):-1].min()

                key = f"{pair}_{tf}"
                pair_state = state.get(key, {})

                utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                # ===== EMA CROSS =====
                if prev.ema20 <= prev.ema50 and curr.ema20 > curr.ema50:

                    if pair_state.get("ema") != "BUY":

                        send_telegram(
                            f"🟢 <b>BUY | EMA 20 Cross Above EMA 50</b>\n\n"
                            f"📊 Pair: {pair}\n"
                            f"⏱ Timeframe: {tf}\n"
                            f"💰 Price: {curr.close:.2f}\n"
                            f"🕒 UTC: {utc}"
                        )

                        pair_state["ema"] = "BUY"

                elif prev.ema20 >= prev.ema50 and curr.ema20 < curr.ema50:

                    if pair_state.get("ema") != "SELL":

                        send_telegram(
                            f"🔴 <b>SELL | EMA 20 Cross Below EMA 50</b>\n\n"
                            f"📊 Pair: {pair}\n"
                            f"⏱ Timeframe: {tf}\n"
                            f"💰 Price: {curr.close:.2f}\n"
                            f"🕒 UTC: {utc}"
                        )

                        pair_state["ema"] = "SELL"

                # ===== BREAKOUT =====
                if prev.close <= swing_high and curr.close > swing_high:

                    if pair_state.get("breakout") != "BULLISH":

                        send_telegram(
                            f"🚀 <b>BULLISH BREAKOUT</b>\n\n"
                            f"📊 Pair: {pair}\n"
                            f"⏱ Timeframe: {tf}\n"
                            f"📈 Level: {swing_high:.2f}\n"
                            f"💰 Price: {curr.close:.2f}\n"
                            f"🕒 UTC: {utc}"
                        )

                        pair_state["breakout"] = "BULLISH"

                elif prev.close >= swing_low and curr.close < swing_low:

                    if pair_state.get("breakout") != "BEARISH":

                        send_telegram(
                            f"📉 <b>BEARISH BREAKDOWN</b>\n\n"
                            f"📊 Pair: {pair}\n"
                            f"⏱ Timeframe: {tf}\n"
                            f"📉 Level: {swing_low:.2f}\n"
                            f"💰 Price: {curr.close:.2f}\n"
                            f"🕒 UTC: {utc}"
                        )

                        pair_state["breakout"] = "BEARISH"

                state[key] = pair_state

            except Exception as e:
                print(f"Error {pair} {tf}: {e}")

    save_state(state)


if __name__ == "__main__":
    main()
