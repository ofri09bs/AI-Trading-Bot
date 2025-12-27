import ccxt
import pandas as pd
import numpy as np
import joblib 
import time
import warnings
from datetime import datetime
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
import os

warnings.filterwarnings('ignore')

SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'       
MODEL_FILE = 'quantum_model.pkl'
LOG_FILE = 'quantum_trades_log.csv'
THRESHOLD = 0.52        # optimal threshold from training
BALANCE = 1000          # virtual money for trading
TRADE_AMOUNT = 100      # trade size per position
TARGET_PROFIT = 0.025   # 2.5%
STOP_LOSS = 0.015       # 1.5%

print(f"[INIT] Loading Quantum Brain: {MODEL_FILE}...")
try:
    model = joblib.load(MODEL_FILE)
    print("[INIT] Model loaded successfully! 🧠")
except Exception as e:
    print(f"[ERROR] Could not load model: {e}")
    exit()


if os.path.exists(LOG_FILE):
    try:
        df_history = pd.read_csv(LOG_FILE)
        print(f"[INIT] Loaded trade history: {len(df_history)} trades found.")
        BALANCE = df_history.iloc[-1]['Balance']
    except Exception as e:
        print(f"[WARN] Could not read log file: {e}")
else:
    print("[INIT] No existing trade log found. Creating new one.")


position = None # None, 'LONG', or 'SHORT'
entry_price = 0
entry_time = None
exchange = ccxt.binance()


def log_trade(exit_time, exit_price, pnl_pct, closing_reason):
    global position, entry_time, entry_price, BALANCE
    
    trade_data = {
        'Entry Time': entry_time,
        'Exit Time': exit_time,
        'Type': position, # LONG / SHORT
        'Entry Price': entry_price,
        'Exit Price': exit_price,
        'PnL (%)': round(pnl_pct * 100, 2), #PnL = Profit and Loss percentage
        'Reason': closing_reason, # TP / SL
        'Balance': round(BALANCE, 2)
    }
    
    df_new = pd.DataFrame([trade_data])
    
    if not os.path.isfile(LOG_FILE):
        df_new.to_csv(LOG_FILE, index=False)
    else:
        df_new.to_csv(LOG_FILE, mode='a', header=False, index=False)
        
    print(f"[LOG] Trade saved to {LOG_FILE} ✅")


def get_live_data():
    exchange = ccxt.binance()
    try:
        bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=300) 
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"[NET ERROR] {e}")
        return None

def extract_features(df):
    #Must be 100% identical to the training function
    df = df.copy()

    # MACD 
    macd = MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()

    # EMA 50/200 
    df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['ema_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
    df['dist_ema_50'] = (df['close'] - df['ema_50']) / df['ema_50']
    df['dist_ema_200'] = (df['close'] - df['ema_200']) / df['ema_200']
    
    df['trend_signal'] = np.where(df['ema_50'] > df['ema_200'], 1, 0)

    # ADX
    adx = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['adx'] = adx.adx()

    # --- 2. Momentum Indicators ---

    # RSI
    rsi = RSIIndicator(close=df['close'], window=14)
    df['rsi'] = rsi.rsi()

    # --- 3. Volatility Indicators ---

    # Bollinger Bands
    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_width'] = bb.bollinger_wband() 
    df['bb_pos'] = bb.bollinger_pband()   

    # ATR 
    atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr_pct'] = atr.average_true_range() / df['close']

    # --- 4. Custom Features ---
    df['vol_change'] = df['volume'].pct_change()
    df['candle_range'] = (df['high'] - df['low']) / df['close']

    df.dropna(inplace=True)
    return df


def emergency_close():
    global position, BALANCE
    
    if position is None:
        print("\n[STOP] No open positions. Exiting gracefully.")
        return

    print(f"\n[STOP] ⚠️ MANUAL STOP DETECTED! Closing {position} position immediately...")
    
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        current_price = ticker['last']
        
        pnl = 0
        if position == 'LONG':
            pnl = (current_price - entry_price) / entry_price
        elif position == 'SHORT':
            pnl = (entry_price - current_price) / entry_price
            
        if pnl >= 0:
            BALANCE += TRADE_AMOUNT * pnl
        else:
            BALANCE -= TRADE_AMOUNT * abs(pnl)
            
        color = "\033[92m" if pnl > 0 else "\033[91m"
        print(f"[STOP] Sold at {current_price}. Final PnL: {color}{pnl*100:.2f}%\033[0m. Balance: {BALANCE:.2f}")
        
        log_trade(datetime.now(), current_price, pnl, "MANUAL STOP ⚠️")
        
    except Exception as e:
        print(f"[CRITICAL ERROR] Could not fetch price to close trade: {e}")
        log_trade(datetime.now(), 0, 0, "ERROR CLOSING")

def run_live_bot():
    global BALANCE, position, entry_price, entry_time
    
    feature_cols = ['rsi', 'trend_signal', 'macd_hist', 'adx', 'atr_pct', 'bb_width', 'bb_pos', 'vol_change', 'dist_ema_50', 'dist_ema_200']

    print(f"--- QUANTUM LIVE BOT STARTED ---")
    print(f"Tracking: {SYMBOL} | Balance: {BALANCE}$ | Threshold: {THRESHOLD}")
    try:

        while True:
            #1. getting data
            df = get_live_data()
            if df is None:
                time.sleep(10)
                continue
            
            # 2. prosessing data
            df_processed = extract_features(df)
            current_data = df_processed.iloc[-1] 
            current_price = current_data['close']
        
            # preparing input for model (must be DataFrame)
            input_row = pd.DataFrame([current_data[feature_cols].values], columns=feature_cols)
        
            # 3. predicting
            # probs = [probability of 0, probability of Long, probability of Short]
            probs = model.predict_proba(input_row)[0]
            prob_long = probs[1]
            prob_short = probs[2]
        
            timestamp = datetime.now().strftime("%H:%M:%S")
        
            # status display
            status_color = "\033[90m" 
            if prob_long > THRESHOLD: status_color = "\033[92m" 
            if prob_short > THRESHOLD: status_color = "\033[91m" 
        
            print(f"[{timestamp}] Price: {current_price:.2f} | Long: {prob_long:.2f} | Short: {prob_short:.2f} | {status_color}Hold\033[0m", end="\r")

            # --- managing open position ---
            if position is not None:
                pnl = 0
                if position == 'LONG':
                    pnl = (current_price - entry_price) / entry_price
                elif position == 'SHORT':
                    pnl = (entry_price - current_price) / entry_price
            
            
                color = "\033[92m" if pnl > 0 else "\033[91m"
                print(f"                                                  | Open {position}: {color}{pnl*100:.2f}%\033[0m", end="\r")

                closed_trade = False
                reason = ""
            
                if pnl >= TARGET_PROFIT:
                    BALANCE += TRADE_AMOUNT * pnl
                    reason = "TAKE PROFIT"
                    closed_trade = True
                    print(f"\n[{timestamp}] 💰 TAKE PROFIT ({position})! Closed at {current_price}. PnL: {pnl*100:.2f}%. Balance: {BALANCE:.2f}$")

                elif pnl <= -STOP_LOSS:
                    BALANCE -= TRADE_AMOUNT * abs(pnl)
                    reason = "STOP LOSS"
                    closed_trade = True 
                    print(f"\n[{timestamp}] 🛑 STOP LOSS ({position}). Closed at {current_price}. PnL: {pnl*100:.2f}%. Balance: {BALANCE:.2f}$")
                    position = None

                if closed_trade:
                    log_trade(datetime.now(), current_price, pnl, reason)
                    position = None
                    entry_price = 0
                    entry_time = None

        
            elif position is None:
                if prob_long > THRESHOLD and prob_long > prob_short:
                    print(f"\n[{timestamp}] 🚀 ENTERING LONG! Confidence: {prob_long:.2f}")
                    position = 'LONG'
                    entry_price = current_price
                    entry_time = datetime.now()
            
                elif prob_short > THRESHOLD and prob_short > prob_long:
                    print(f"\n[{timestamp}] 📉 ENTERING SHORT! Confidence: {prob_short:.2f}")
                    position = 'SHORT'
                    entry_price = current_price
                    entry_time = datetime.now()

            time.sleep(10)

    except KeyboardInterrupt:
        emergency_close()
        print("[EXIT] Bot shutdown complete. Goodbye! 👋")

if __name__ == "__main__":
    run_live_bot()
