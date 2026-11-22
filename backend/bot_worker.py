import argparse
import time
import MetaTrader5 as mt5
from db import add_log
from security import decrypt_text
from strategy import TradeSignal, evaluate_trend_rsi_atr

def get_filling_mode(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    if info.filling_mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if info.filling_mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def has_open_position(symbol: str, magic: int) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return False
    return any(p.magic == magic for p in positions)

def compute_sl_tp(symbol: str, side: str, entry_price: float, sl_dist: float, tp_dist: float) -> tuple[float, float] | None:
    info = mt5.symbol_info(symbol)
    if info is None:
        return None

    digits = info.digits
    point = info.point
    min_stop_dist = max(info.trade_stops_level * point, point * 5)

    if sl_dist < min_stop_dist:
        sl_dist = min_stop_dist
    if tp_dist < min_stop_dist:
        tp_dist = min_stop_dist

    if side == "BUY":
        sl = round(entry_price - sl_dist, digits)
        tp = round(entry_price + tp_dist, digits)
        if sl >= entry_price or tp <= entry_price:
            return None
    else:
        sl = round(entry_price + sl_dist, digits)
        tp = round(entry_price - tp_dist, digits)
        if sl <= entry_price or tp >= entry_price:
            return None

    return sl, tp

def place_order(user_id: str, symbol: str, signal: TradeSignal, lot: float, magic: int) -> None:
    if not mt5.symbol_select(symbol, True):
        add_log(user_id, "WARN", f"Could not select symbol {symbol}")
        return

    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        add_log(user_id, "WARN", f"Missing symbol info or tick for {symbol}")
        return

    spread_points = (tick.ask - tick.bid) / info.point
    if spread_points > 30:
        add_log(user_id, "WARN", f"Skipped {signal.side} {symbol}: spread too wide ({spread_points:.1f} pts)")
        return

    if signal.side == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = round(tick.ask, info.digits)
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = round(tick.bid, info.digits)

    sl_tp = compute_sl_tp(symbol, signal.side, price, signal.sl_distance, signal.tp_distance)
    if sl_tp is None:
        add_log(user_id, "WARN", f"Skipped {signal.side} {symbol}: invalid SL/TP calculation")
        return

    sl, tp = sl_tp

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": "TrendRsiAtr",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        add_log(user_id, "ERROR", f"order_send returned None: {mt5.last_error()}")
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        add_log(user_id, "WARN", f"Order rejected ({signal.side} {symbol}): retcode={result.retcode} ({result.comment})")
    else:
        add_log(
            user_id,
            "INFO",
            f"Filled {signal.side} {lot} {symbol} @ {price} | SL={sl} TP={tp} | {signal.reason}",
        )

def run_worker(
    user_id: str,
    terminal_path: str,
    login: int,
    encrypted_password: str,
    server: str,
    symbol: str,
    lot: float,
    max_daily_loss: float,
) -> None:
    password = decrypt_text(encrypted_password)
    magic = 77001

    add_log(user_id, "INFO", f"Starting MT5 worker for login={login} server={server} symbol={symbol}")

    initialized = mt5.initialize(
        path=terminal_path,
        login=login,
        password=password,
        server=server,
        portable=True,
    )
    if not initialized:
        add_log(user_id, "ERROR", f"MT5 initialize/login failed: {mt5.last_error()}")
        return

    account = mt5.account_info()
    if account is None:
        add_log(user_id, "ERROR", "Failed to read MT5 account_info after login")
        mt5.shutdown()
        return

    start_equity = float(account.equity)
    add_log(user_id, "INFO", f"Connected! Balance={account.balance:.2f} Equity={start_equity:.2f} {account.currency}")

    try:
        while True:
            acc = mt5.account_info()
            if acc is None:
                add_log(user_id, "WARN", "Lost account info, retrying connection...")
                time.sleep(5)
                continue

            drawdown = start_equity - float(acc.equity)
            if drawdown >= max_daily_loss:
                add_log(user_id, "WARN", f"Max daily loss hit ({drawdown:.2f} >= {max_daily_loss:.2f}). Stopping bot.")
                break

            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 250)
            signal = evaluate_trend_rsi_atr(rates, sl_atr_mult=1.5, rr_ratio=2.0)
            if signal and not has_open_position(symbol, magic):
                place_order(user_id, symbol, signal, lot, magic)

            time.sleep(10)
    except KeyboardInterrupt:
        add_log(user_id, "INFO", "Worker stopped by signal.")
    finally:
        mt5.shutdown()
        add_log(user_id, "INFO", "MT5 connection closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--login", type=int, required=True)
    parser.add_argument("--enc-password", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--lot", type=float, required=True)
    parser.add_argument("--max-daily-loss", type=float, required=True)
    args = parser.parse_args()

    run_worker(
        user_id=args.user_id,
        terminal_path=args.terminal_path,
        login=args.login,
        encrypted_password=args.enc_password,
        server=args.server,
        symbol=args.symbol,
        lot=args.lot,
        max_daily_loss=args.max_daily_loss,
    )