from fyers_apiv3.FyersWebsocket import data_ws
import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.parse

# ============================================================
# NIFTY V8 ALERT ENGINE
# ============================================================
#
# ALERTS ONLY
# NO ORDER PLACEMENT
#
# Mark Candle:
#     abs(Open - Close) <= 0.90
#
# BUY:
#     Close > active Mark High
#
# SELL:
#     Close < active Mark Low
#
# LONG EXIT:
#     Close < active Mark Close
#
# SHORT EXIT:
#     Close > active Mark Close
#
# Opposite breakout has priority over normal exit.
#
# Latest qualifying candle always becomes the new Mark.
#
# ============================================================


# ============================================================
# FILES
# ============================================================

# In the cloud version, credentials come from environment variables.
# GitHub Actions will provide these through encrypted repository secrets.
FYERS_TOKEN_FILE = None
TELEGRAM_TOKEN_FILE = None
TELEGRAM_CHAT_FILE = None
STATE_FILE = Path(os.getenv("V8_STATE_FILE", "v8_state.json"))
STOP_HOUR = int(os.getenv("V8_STOP_HOUR", "15"))
STOP_MINUTE = int(os.getenv("V8_STOP_MINUTE", "35"))


# ============================================================
# SETTINGS
# ============================================================

SYMBOL = "NSE:NIFTY50-INDEX"

MARK_BODY_MAX = 0.90

IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================
# LOAD CREDENTIALS
# ============================================================

fyers_token = os.environ["FYERS_ACCESS_TOKEN"].strip()
telegram_token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
telegram_chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    try:

        params = urllib.parse.urlencode({
            "chat_id": telegram_chat_id,
            "text": message
        })

        url = (
            "https://api.telegram.org/bot"
            + telegram_token
            + "/sendMessage?"
            + params
        )

        urllib.request.urlopen(url, timeout=10).read()

        print("TELEGRAM SENT")

    except Exception as e:

        print("TELEGRAM ERROR:", e)


# ============================================================
# POSITION STATE
# ============================================================

position = "FLAT"

# Possible values:
#
# FLAT
# LONG
# SHORT


# ============================================================
# ACTIVE MARK
# ============================================================

mark_high = None
mark_low = None
mark_close = None
mark_time = None


# ============================================================
# DAY STATE
# ============================================================

current_day = None


# ============================================================
# LIVE 5-MINUTE CANDLE
# ============================================================

current_bucket = None

candle_open = None
candle_high = None
candle_low = None
candle_close = None


# ============================================================
# HELPERS
# ============================================================

def bucket_time(dt):

    minute = (dt.minute // 5) * 5

    return dt.replace(
        minute=minute,
        second=0,
        microsecond=0
    )


def reset_day(day):

    global current_day
    global position

    global mark_high
    global mark_low
    global mark_close
    global mark_time

    current_day = day

    position = "FLAT"

    mark_high = None
    mark_low = None
    mark_close = None
    mark_time = None

    print("")
    print("========================================")
    print("NEW TRADING DAY")
    print(f"DATE: {day}")
    print("POSITION RESET: FLAT")
    print("MARK RESET")
    print("========================================")
    print("")


def save_state():
    state = {
        "current_day": current_day.isoformat() if current_day else None,
        "position": position,
        "mark_high": mark_high,
        "mark_low": mark_low,
        "mark_close": mark_close,
        "mark_time": mark_time,
        "current_bucket": current_bucket.isoformat() if current_bucket else None,
        "candle_open": candle_open,
        "candle_high": candle_high,
        "candle_low": candle_low,
        "candle_close": candle_close,
    }
    STATE_FILE.write_text(json.dumps(state))
    print(f"STATE SAVED: {STATE_FILE}")


def load_state():
    global current_day, position
    global mark_high, mark_low, mark_close, mark_time
    global current_bucket
    global candle_open, candle_high, candle_low, candle_close

    if not STATE_FILE.exists():
        return False

    try:
        state = json.loads(STATE_FILE.read_text())

        current_day = (
            datetime.fromisoformat(state["current_day"]).date()
            if state.get("current_day") else None
        )
        position = state.get("position", "FLAT")
        mark_high = state.get("mark_high")
        mark_low = state.get("mark_low")
        mark_close = state.get("mark_close")
        mark_time = state.get("mark_time")
        current_bucket = (
            datetime.fromisoformat(state["current_bucket"])
            if state.get("current_bucket") else None
        )
        candle_open = state.get("candle_open")
        candle_high = state.get("candle_high")
        candle_low = state.get("candle_low")
        candle_close = state.get("candle_close")

        print("STATE RESTORED")
        print(f"POSITION: {position}")
        if mark_time:
            print(f"MARK TIME: {mark_time}")
        return True

    except Exception as e:
        print("STATE RESTORE ERROR:", e)
        return False


def should_stop(dt):
    return (
        dt.hour > STOP_HOUR
        or (dt.hour == STOP_HOUR and dt.minute >= STOP_MINUTE)
    )


def send_signal(signal, candle_time, price):

    message = (
        f"NIFTY V8 ALERT\n"
        f"Signal: {signal}\n"
        f"Time: {candle_time}\n"
        f"NIFTY: {price:.2f}\n"
        f"Position: {position}"
    )

    print("")
    print("########################################")
    print(message)
    print("########################################")
    print("")

    send_telegram(message)


# ============================================================
# PROCESS COMPLETED CANDLE
# ============================================================

def process_completed_candle(
    candle_time,
    open_price,
    high_price,
    low_price,
    close_price
):

    global position

    global mark_high
    global mark_low
    global mark_close
    global mark_time

    candle_label = candle_time.strftime("%H:%M")

    body = abs(open_price - close_price)

    print("")
    print("----------------------------------------")
    print(f"CANDLE {candle_label}")
    print(f"O: {open_price:.2f}")
    print(f"H: {high_price:.2f}")
    print(f"L: {low_price:.2f}")
    print(f"C: {close_price:.2f}")
    print(f"BODY: {body:.2f}")
    print(f"POSITION: {position}")

    if mark_high is not None:

        print(
            f"ACTIVE MARK | "
            f"H: {mark_high:.2f} "
            f"L: {mark_low:.2f} "
            f"C: {mark_close:.2f} "
            f"TIME: {mark_time}"
        )

    else:

        print("ACTIVE MARK: NONE")

    # ========================================================
    # EOD
    # ========================================================

    # 15:25 candle is the final regular-session candle.
    # It must be exited at EOD and must NOT create a new
    # signal/mark after the session ends.

    is_eod_candle = (
        candle_time.hour == 15
        and candle_time.minute == 25
    )

    if is_eod_candle:

        if position == "LONG":

            send_signal(
                "EOD EXIT LONG",
                candle_label,
                close_price
            )

        elif position == "SHORT":

            send_signal(
                "EOD EXIT SHORT",
                candle_label,
                close_price
            )

        else:

            print("EOD: NO OPEN POSITION")

        position = "FLAT"

        print("EOD COMPLETE")
        print("----------------------------------------")

        return

    # ========================================================
    # SIGNAL LOGIC
    # ========================================================

    signal_generated = False

    # --------------------------------------------------------
    # LONG POSITION
    # --------------------------------------------------------

    if position == "LONG":

        # Opposite breakout has priority.
        if (
            mark_low is not None
            and close_price < mark_low
        ):

            send_signal(
                "REVERSAL LONG -> SHORT",
                candle_label,
                close_price
            )

            position = "SHORT"

            signal_generated = True

        # Normal LONG exit
        elif (
            mark_close is not None
            and close_price < mark_close
        ):

            send_signal(
                "EXIT LONG",
                candle_label,
                close_price
            )

            position = "FLAT"

            signal_generated = True

    # --------------------------------------------------------
    # SHORT POSITION
    # --------------------------------------------------------

    elif position == "SHORT":

        # Opposite breakout has priority.
        if (
            mark_high is not None
            and close_price > mark_high
        ):

            send_signal(
                "REVERSAL SHORT -> LONG",
                candle_label,
                close_price
            )

            position = "LONG"

            signal_generated = True

        # Normal SHORT exit
        elif (
            mark_close is not None
            and close_price > mark_close
        ):

            send_signal(
                "EXIT SHORT",
                candle_label,
                close_price
            )

            position = "FLAT"

            signal_generated = True

    # --------------------------------------------------------
    # FLAT POSITION
    # --------------------------------------------------------

    elif position == "FLAT":

        # BUY breakout
        if (
            mark_high is not None
            and close_price > mark_high
        ):

            send_signal(
                "BUY",
                candle_label,
                close_price
            )

            position = "LONG"

            signal_generated = True

        # SELL breakout
        elif (
            mark_low is not None
            and close_price < mark_low
        ):

            send_signal(
                "SELL",
                candle_label,
                close_price
            )

            position = "SHORT"

            signal_generated = True

    # ========================================================
    # NEW MARK CANDLE
    # ========================================================

    # Every qualifying candle becomes the NEW mark.
    #
    # This happens AFTER the candle has been checked against
    # the previous mark, so the mark candle cannot trigger
    # its own breakout.

    if body <= MARK_BODY_MAX:

        mark_high = high_price
        mark_low = low_price
        mark_close = close_price
        mark_time = candle_label

        print("")
        print(">>> NEW MARK CANDLE <<<")
        print(f"TIME : {candle_label}")
        print(f"HIGH : {mark_high:.2f}")
        print(f"LOW  : {mark_low:.2f}")
        print(f"CLOSE: {mark_close:.2f}")
        print(f"BODY : {body:.2f}")
        print("")

    else:

        print("Not a Mark Candle.")

    print(f"FINAL POSITION: {position}")
    print("----------------------------------------")


# ============================================================
# FINALIZE CURRENT 5-MINUTE CANDLE
# ============================================================

def finalize_candle():

    global candle_open
    global candle_high
    global candle_low
    global candle_close
    global current_bucket

    if candle_open is None:

        return

    process_completed_candle(
        current_bucket,
        candle_open,
        candle_high,
        candle_low,
        candle_close
    )


# ============================================================
# PROCESS LIVE PRICE
# ============================================================

def process_price(price, timestamp):

    global current_day

    global current_bucket

    global candle_open
    global candle_high
    global candle_low
    global candle_close

    dt = (
        datetime
        .fromtimestamp(
            timestamp,
            tz=timezone.utc
        )
        .astimezone(IST)
    )

    # --------------------------------------------------------
    # CLOUD JOB STOP
    # --------------------------------------------------------

    if should_stop(dt):
        save_state()
        print("V8 SESSION WINDOW COMPLETE")
        raise SystemExit(0)

    # --------------------------------------------------------
    # NEW DAY RESET
    # --------------------------------------------------------

    if current_day != dt.date():

        reset_day(dt.date())

        current_bucket = None

        candle_open = None
        candle_high = None
        candle_low = None
        candle_close = None

    # --------------------------------------------------------
    # IGNORE OUTSIDE REGULAR SESSION
    # --------------------------------------------------------

    market_open = (
        dt.hour > 9
        or (
            dt.hour == 9
            and dt.minute >= 15
        )
    )

    market_close = (
        dt.hour < 15
        or (
            dt.hour == 15
            and dt.minute < 30
        )
    )

    if not (market_open and market_close):

        return

    new_bucket = bucket_time(dt)

    # --------------------------------------------------------
    # FIRST CANDLE
    # --------------------------------------------------------

    if current_bucket is None:

        current_bucket = new_bucket

        candle_open = price
        candle_high = price
        candle_low = price
        candle_close = price

        print(
            f"NEW CANDLE "
            f"{current_bucket.strftime('%H:%M')} "
            f"| {price:.2f}"
        )

        return

    # --------------------------------------------------------
    # NEW 5-MINUTE CANDLE
    # --------------------------------------------------------

    if new_bucket > current_bucket:

        finalize_candle()

        current_bucket = new_bucket

        candle_open = price
        candle_high = price
        candle_low = price
        candle_close = price

        print(
            f"NEW CANDLE "
            f"{current_bucket.strftime('%H:%M')} "
            f"| {price:.2f}"
        )

        return

    # --------------------------------------------------------
    # SAME CANDLE
    # --------------------------------------------------------

    candle_high = max(candle_high, price)
    candle_low = min(candle_low, price)
    candle_close = price


# ============================================================
# FYERS WEBSOCKET
# ============================================================

def on_message(message):

    try:

        if not isinstance(message, dict):

            return

        if "ltp" not in message:

            return

        price = float(message["ltp"])

        timestamp = message.get("timestamp")

        if timestamp is None:

            timestamp = datetime.now(
                timezone.utc
            ).timestamp()

        process_price(
            price,
            timestamp
        )

    except Exception as e:

        print(
            "MESSAGE ERROR:",
            e
        )


def on_error(message):

    print(
        "FYERS ERROR:",
        message
    )


def on_close(message):

    print(
        "FYERS CONNECTION CLOSED:",
        message
    )


def on_connect():

    print("")
    print("========================================")
    print("CONNECTED TO FYERS")
    print("SUBSCRIBING TO NIFTY 50...")
    print("========================================")

    fyers.subscribe(
        symbols=[SYMBOL],
        data_type="SymbolUpdate"
    )

    print(
        "NIFTY 50 SUBSCRIPTION SUCCESSFUL"
    )

    print(
        "NIFTY V8 ALERT ENGINE RUNNING"
    )

    print(
        f"MARK BODY THRESHOLD: {MARK_BODY_MAX:.2f}"
    )

    print(
        "TELEGRAM ALERTS ENABLED"
    )

    print(
        "NO ORDERS WILL BE PLACED"
    )

    print(
        "Press CTRL+C to stop."
    )

    print("")


# ============================================================
# START
# ============================================================

print("")
print("==============================================")
print("NIFTY V8 ALERT ENGINE")
print("==============================================")
print("SYMBOL:", SYMBOL)
print("MARK BODY <= ", MARK_BODY_MAX)
print("MODE: ALERTS ONLY")
print("ORDERS: DISABLED")
print(f"STOP TIME: {STOP_HOUR:02d}:{STOP_MINUTE:02d} IST")
print("MODE: CLOUD / GITHUB ACTIONS")
print("==============================================")
print("")

load_state()

fyers = data_ws.FyersDataSocket(
    access_token=fyers_token,
    log_path="",
    litemode=False,
    write_to_file=False,
    reconnect=True,
    on_connect=on_connect,
    on_close=on_close,
    on_error=on_error,
    on_message=on_message
)

fyers.connect()