import ccxt
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib 
import time
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
import warnings

warnings.filterwarnings(action='ignore', category=FutureWarning)

SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'      
TARGET_PROFIT = 0.025 
STOP_LOSS = 0.015      
LOOK_AHEAD = 12       
FEE = 0.002

def load_data(symbol='BTC/USDT', timeframe=TIMEFRAME, days_back=365):
    print("Loading data...")
    exchange = ccxt.binance()

    since = exchange.milliseconds() - (days_back * 24 * 60 * 60 * 1000)
    all_candles = []

    while since < exchange.milliseconds():
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
            if not candles:
                break

            all_candles += candles
            since = candles[-1][0] + 1  # Move to the next timestamp
            print(f" -> Fetched {len(candles)} candles... Total: {len(all_candles)}")

            time.sleep(0.1) 

        except Exception as e:
            print("Error fetching data:", e)
            break

    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    df.drop_duplicates(subset=['timestamp'], inplace=True)
    return df


def backtest_logic(df_test, probs, threshold=0.60):
    capital = 1.0
    trades = []
    wins = 0
    
    for i in range(len(df_test) - LOOK_AHEAD):
        prob_long = probs[i][1]
        prob_short = probs[i][2]
        
        current_close = df_test.iloc[i]['close']
        future_candles = df_test.iloc[i+1 : i+1+LOOK_AHEAD]
        
        pnl = 0
        trade_taken = False
        
        # ---  Long Logic ---
        if prob_long > threshold and prob_long > prob_short:
            tp = current_close * (1 + TARGET_PROFIT)
            sl = current_close * (1 - STOP_LOSS)
            exit_price = future_candles.iloc[-1]['close']
            
            for _, row in future_candles.iterrows():
                if row['low'] <= sl:
                    exit_price = sl
                    break
                if row['high'] >= tp:
                    exit_price = tp
                    break
            
            pnl = (exit_price - current_close) / current_close
            trade_taken = True
            
        # ---  Short Logic ---
        elif prob_short > threshold and prob_short > prob_long:
            tp = current_close * (1 - TARGET_PROFIT)
            sl = current_close * (1 + STOP_LOSS)
            exit_price = future_candles.iloc[-1]['close']
            
            for _, row in future_candles.iterrows():
                if row['high'] >= sl:
                    exit_price = sl
                    break
                if row['low'] <= tp:
                    exit_price = tp
                    break
            
            # Profit in short is reversed: entry price minus exit price
            pnl = (current_close - exit_price) / current_close
            trade_taken = True
            
        if trade_taken:
            net_pnl = pnl - FEE
            capital *= (1 + net_pnl)
            trades.append(net_pnl)
            if net_pnl > 0: wins += 1

    return capital, trades, wins



def extract_features(df):
    df = df.copy()

    # --- 1. Trend Indicators ---
    
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

    # --- 5. Target Logic (SHORT AND LONG) ---
    targets = []
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    
    for i in range(len(df) - LOOK_AHEAD):
        entry = closes[i]

        long_tp = entry * (1 + TARGET_PROFIT)
        long_sl = entry * (1 - STOP_LOSS)
        
        short_tp = entry * (1 - TARGET_PROFIT)
        short_sl = entry * (1 + STOP_LOSS)
        
        outcome = 0 
        
        for j in range(1, LOOK_AHEAD + 1):
            curr_high = highs[i+j]
            curr_low = lows[i+j]
            
            if curr_low > long_sl and curr_high >= long_tp:
                outcome = 1
                break
            
            if curr_high < short_sl and curr_low <= short_tp:
                outcome = 2
                break
                
            if curr_low <= long_sl or curr_high >= short_sl:
                outcome = 0
                break
                
        targets.append(outcome)
    
    targets = targets + [0] * LOOK_AHEAD
    df['target'] = targets
    df.dropna(inplace=True)
    return df

def train_model():
    
    df = load_data()
    if len(df) < 1000:
        print("Not enough data fetched.")
        return

    features_df = extract_features(df)

    longs = len(features_df[features_df['target'] == 1])
    shorts = len(features_df[features_df['target'] == 2])
    print(f"Signals found -> Longs: {longs} | Shorts: {shorts}")

    buy_signals = features_df['target'].sum()
    print(f"Dataset: {len(df)} rows | Positive Signals: {buy_signals} ({(buy_signals/len(df))*100:.1f}%)")

    if buy_signals < 50:
        print("Not enough profitable trades found in history to train. Try lowering the threshold.")
        return

    feature_cols = ['rsi', 'trend_signal', 'macd_hist', 'adx', 'atr_pct', 'bb_width', 'bb_pos', 'vol_change', 'dist_ema_50', 'dist_ema_200']

    X = features_df[feature_cols]
    y = features_df['target']

    split = int(len(features_df) * 0.85)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    sample_weights = np.zeros(len(y_train))
    
    sample_weights[y_train == 0] = 1.0 
    
    sample_weights[y_train == 1] = 20.0 
    sample_weights[y_train == 2] = 20.0

    print(f"Training Multi-Class XGBoost...")
    model = XGBClassifier(
        n_estimators=800,
        learning_rate=0.01,
        max_depth=8,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='multi:softprob', # Multi-class classification
        num_class=3,                # 0, 1, 2
        random_state=42,
        eval_metric='mlogloss',
        min_child_weight=2
    )

    model.fit(X_train, y_train, sample_weight=sample_weights)

    probs = model.predict_proba(X_test)
    best_thresh = 0.5
    best_cap = 0   

    print("\nFinding optimal threshold...")
    for th in np.arange(0.40, 0.90, 0.02):
        cap, trades, _ = backtest_logic(features_df.iloc[split:].reset_index(drop=True), probs, threshold=th)
        if cap > best_cap and len(trades) >= 10:
            best_cap = cap
            best_thresh = th
            
    print(f"Optimal Threshold Found: {best_thresh:.2f}")

    final_cap, final_trades, final_wins = backtest_logic(features_df.iloc[split:].reset_index(drop=True), probs, threshold=best_thresh)

    print("\n💰 FINAL BACKTEST RESULTS")
    print(f"Starting Capital: 1.0")
    print(f"Ending Capital:   {final_cap:.4f}")
    print(f"Total Return:     {(final_cap - 1) * 100:.2f}%")
    print(f"Total Trades:     {len(final_trades)}")
    print(f"Winning Trades:   {final_wins} ({(final_wins / len(final_trades)) * 100:.2f}%)")

    if len(final_trades) > 0:
        win_rate = final_wins / len(final_trades)
        print(f"Win Rate:         {win_rate*100:.1f}%")


    print("\n------ Classification Report ------")
    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))
    print("Confusion Matrix:")      
    cm = confusion_matrix(y_test, y_pred)
    print(cm)

    print("\n------ Feature Importances ------")
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print(importances)

    joblib.dump(model, 'quantum_model.pkl')


if __name__ == "__main__":
    train_model()