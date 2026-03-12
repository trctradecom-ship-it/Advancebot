import ccxt
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime

# ================= TELEGRAM =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003734649641"
# ===========================================

PAIRS = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT"]
TIMEFRAMES = ["5m","15m","30m","1h","4h","1d"]

EMA_FAST = 20
EMA_SLOW = 50
LOOKBACK = 20

STATE_FILE = "last_signal.json"
SIGNAL_COOLDOWN = 7200   # 2 hours


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


# ================= STATE =================
def load_state():

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE,"r") as f:
            return json.load(f)

    return {}


def save_state(state):

    with open(STATE_FILE,"w") as f:
        json.dump(state,f,indent=2)


# ================= DATA =================
def fetch_data(exchange,pair,tf):

    for i in range(3):

        try:

            ohlcv = exchange.fetch_ohlcv(pair,tf,limit=200)

            df = pd.DataFrame(
                ohlcv,
                columns=["time","open","high","low","close","volume"]
            )

            return df

        except Exception as e:

            print(f"Retry {pair} {tf}")
            time.sleep(2)

    return None


# ================= MAIN =================
def main():

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing")

    exchange = ccxt.mexc({
        "enableRateLimit": True
    })

    state = load_state()
    now = int(time.time())

    # BOT START MESSAGE
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":

        send_telegram(
            "🤖 <b>Crypto Signals Bot Started</b>\n"
            "📡 Exchange: MEXC\n"
            "⚙️ Strategy: EMA 20/50 + Breakout\n"
            "🚀 Status: Manual Start"
        )

    signals = {}

    for pair in PAIRS:
        for tf in TIMEFRAMES:

            try:

                df = fetch_data(exchange,pair,tf)

                if df is None or len(df) < 100:
                    continue

                df["ema20"] = df["close"].ewm(span=EMA_FAST,adjust=False).mean()
                df["ema50"] = df["close"].ewm(span=EMA_SLOW,adjust=False).mean()

                prev2 = df.iloc[-3]
                prev1 = df.iloc[-2]

                utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                swing_high = df["high"].iloc[-(LOOKBACK+2):-2].max()
                swing_low  = df["low"].iloc[-(LOOKBACK+2):-2].min()

                # ================= EMA BUY =================
                if prev2.ema20 <= prev2.ema50 and prev1.ema20 > prev1.ema50:

                    key = f"{pair}_EMA_BUY"

                    if key not in state or now - state[key] > SIGNAL_COOLDOWN:

                        signals.setdefault(key,{
                            "pair":pair,
                            "type":"EMA_BUY",
                            "price":prev1.close,
                            "timeframes":[],
                            "utc":utc
                        })

                        signals[key]["timeframes"].append(tf)


                # ================= EMA SELL =================
                elif prev2.ema20 >= prev2.ema50 and prev1.ema20 < prev1.ema50:

                    key = f"{pair}_EMA_SELL"

                    if key not in state or now - state[key] > SIGNAL_COOLDOWN:

                        signals.setdefault(key,{
                            "pair":pair,
                            "type":"EMA_SELL",
                            "price":prev1.close,
                            "timeframes":[],
                            "utc":utc
                        })

                        signals[key]["timeframes"].append(tf)


                # ================= BREAKOUT BUY =================
                if prev1.close > swing_high:

                    key = f"{pair}_BREAKOUT_BUY"

                    if key not in state or now - state[key] > SIGNAL_COOLDOWN:

                        signals.setdefault(key,{
                            "pair":pair,
                            "type":"BREAKOUT_BUY",
                            "price":prev1.close,
                            "level":swing_high,
                            "timeframes":[],
                            "utc":utc
                        })

                        signals[key]["timeframes"].append(tf)


                # ================= BREAKOUT SELL =================
                elif prev1.close < swing_low:

                    key = f"{pair}_BREAKOUT_SELL"

                    if key not in state or now - state[key] > SIGNAL_COOLDOWN:

                        signals.setdefault(key,{
                            "pair":pair,
                            "type":"BREAKOUT_SELL",
                            "price":prev1.close,
                            "level":swing_low,
                            "timeframes":[],
                            "utc":utc
                        })

                        signals[key]["timeframes"].append(tf)

            except Exception as e:
                print(f"Error {pair} {tf}: {e}")


    # ================= SEND SIGNALS =================
    for key,data in signals.items():

        pair = data["pair"]
        price = data["price"]
        utc = data["utc"]
        tfs = data["timeframes"]

        tf_text = ", ".join(sorted(tfs))

        # EMA BUY
        if data["type"] == "EMA_BUY":

            if len(tfs) > 1:

                msg = (
                f"🟢 <b>BUY | EMA 20 Cross Above EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframes: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )

            else:

                msg = (
                f"🟢 <b>BUY | EMA 20 Cross Above EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframe: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )


        # EMA SELL
        elif data["type"] == "EMA_SELL":

            if len(tfs) > 1:

                msg = (
                f"🔴 <b>SELL | EMA 20 Cross Below EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframes: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )

            else:

                msg = (
                f"🔴 <b>SELL | EMA 20 Cross Below EMA 50</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframe: {tf_text}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )


        # BREAKOUT BUY
        elif data["type"] == "BREAKOUT_BUY":

            if len(tfs) > 1:

                msg = (
                f"🚀 <b>BULLISH BREAKOUT</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframes: {tf_text}\n"
                f"📈 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )

            else:

                msg = (
                f"🚀 <b>BULLISH BREAKOUT</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframe: {tf_text}\n"
                f"📈 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )


        # BREAKOUT SELL
        else:

            if len(tfs) > 1:

                msg = (
                f"📉 <b>BEARISH BREAKDOWN</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframes: {tf_text}\n"
                f"📉 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )

            else:

                msg = (
                f"📉 <b>BEARISH BREAKDOWN</b>\n\n"
                f"📊 Pair: {pair}\n"
                f"⏱ Timeframe: {tf_text}\n"
                f"📉 Level: {data['level']:.2f}\n"
                f"💰 Price: {price:.2f}\n"
                f"🕒 UTC: {utc}"
                )

        send_telegram(msg)

        time.sleep(1)

        state[key] = now

    save_state(state)


if __name__ == "__main__":
    main()
