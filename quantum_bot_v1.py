import ccxt.async_support as ccxt
import asyncio
import pandas as pd
import warnings
import time
import os

warnings.simplefilter(action='ignore', category=FutureWarning)

SYMBOL = 'BTC/USDT'
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
STARTING_MONEY = 10000  # Starting balance in USDT
BALANCE = 10000  # Starting balance in USDT
BUY_AMOUNT = 0.001  # Amount of BTC to buy/sell per trade (0.001 BTC)

close_prices = []

exchange_deals = {
    'index': [], 
    'Buy_Price': [], 
    'Sell_Price': [], 
    '(%) Profit': [], 
    'Balance': []
}

def calculate_rsi(prices, period=RSI_PERIOD):
    if len(prices) < period:
        return None
        
    series = pd.Series(prices)
    delta = series.diff()

    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.iloc[-1]


async def analyze_data():

    if len(close_prices) < RSI_PERIOD + 2:
        return None
    
    current_rsi = calculate_rsi(close_prices)
    if pd.isna(current_rsi):
        return None
    
    current_price = close_prices[-1]
    descision = "HOLD"
    color = "\033[0m"

    if current_rsi > RSI_OVERBOUGHT:
        descision = "SELL 🔴"
        color = "\033[91m"  # Red

    elif current_rsi < RSI_OVERSOLD:
        descision = "BUY 🟢"
        color = "\033[92m"  # Green

    print(f"[Time:{time.strftime('%Y-%m-%d %H:%M:%S')}] {color}[RSI: {current_rsi:.2f}] Price: {current_price} => ACTION: {descision}\033[0m")

    return descision


async def run_bot():
    global BALANCE, close_prices, BUY_AMOUNT, exchange_deals
    print(f"--- QUANTUM BOT V2: RSI STRATEGY (Native Mode) ---")
    print(f"Target: {SYMBOL} | Interval: ~1s (Simulation)")
    print("Gathering data...")

    exchange = ccxt.binance()
    buy_index = 0
    sell_index = 0

    try:
        while True:
            try:
                ticker = await exchange.fetch_ticker(SYMBOL)
            except asyncio.CancelledError:
                print("⚠️ fetch_ticker was cancelled, retrying...")
                return None
            except Exception as e:
                print("Error fetching ticker:", e)
                return None
            
            price = ticker['last']
            close_prices.append(price)

            if len(close_prices) > 100:
                close_prices.pop(0)

            decision = await analyze_data()

            if sell_index > 0 and sell_index % 5 == 0: 
                print(f"\n\033[94m[STATUS] Completed Trades: {sell_index} | Current Balance: {BALANCE:.2f} USDT\033[0m")

            if BALANCE <= 0:
                print("Reaching zero balance. Waiting to sell")
                await asyncio.sleep(1)
                continue


            #--------- BUY LOGIC ---------#

            if decision == "BUY 🟢":
                if BALANCE < price * BUY_AMOUNT:

                    print("\033[93m[INFO] Insufficient balance to execute BUY action. Skipping BUY.\033[0m")
                    await asyncio.sleep(1)
                    continue

                exchange_deals['index'].append(buy_index)
                exchange_deals['Buy_Price'].append(price)
                exchange_deals['Sell_Price'].append(0)
                exchange_deals['(%) Profit'].append(0)
                exchange_deals['Balance'].append(round(BALANCE, 2))
                buy_index += 1
                BALANCE -= price * BUY_AMOUNT  # Deduct the cost from balance
                print(f" -> Bought {BUY_AMOUNT} BTC at {price*BUY_AMOUNT} USD , Remaining Balance: {BALANCE:.2f} USD")


            #--------- SELL LOGIC ---------#
                
            elif decision == "SELL 🔴":

                if sell_index >= buy_index:
                    print("\033[93m[INFO] No BTC available to sell. Skipping SELL action.\033[0m")
                    await asyncio.sleep(1)
                    continue

                if buy_index > 0:
                    sell_price = price
                    buy_price = exchange_deals['Buy_Price'][sell_index]

                    # Setting a 2% stop loss
                    if sell_price < buy_price:

                        if sell_price < buy_price * 0.98:
                            print(f"\033[91m[STOP LOSS TRIGGERED] Selling at {sell_price} \033[0m")
                        else:
                            await asyncio.sleep(1)
                            continue


                    profit_percent = ((sell_price - buy_price) / buy_price) * 100
                    profit = (sell_price - buy_price) * BUY_AMOUNT  # Add the revenue to balance
                    
                    BALANCE += sell_price * BUY_AMOUNT  # Add the revenue to balance

                    exchange_deals['Sell_Price'][sell_index] = sell_price
                    exchange_deals['(%) Profit'][sell_index] = round(profit_percent, 2)
                    exchange_deals['Balance'][sell_index] = round(BALANCE, 2)

                    color = "\033[92m" if profit_percent > 0 else "\033[91m"
                    print(f" -> {color}Sold at {sell_price} | Profit: {profit_percent:.2f}%\033[0m")
                    sell_index += 1

            elif decision == "HOLD":
                pass

            else :
                print("\033[93m[INFO] Not enough data to make a decision.\033[0m")

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("\n[INFO] Bot received STOP signal...")

    finally:
        await exchange.close()
        # Selling all remaining BTC at the last price
        if buy_index > sell_index:
            print("[INFO] Closing remaining open positions...")
            remaining_trades = buy_index - sell_index
            last_price = close_prices[-1]
            
            for i in range(remaining_trades):

                if sell_index < len(exchange_deals['Buy_Price']):
                    buy_price = exchange_deals['Buy_Price'][sell_index]
                    profit_percent = ((last_price - buy_price) / buy_price) * 100
                    profit = last_price * BUY_AMOUNT
                    BALANCE += profit

                    exchange_deals['Sell_Price'][sell_index] = last_price
                    exchange_deals['(%) Profit'][sell_index] = round(profit_percent, 2)
                    exchange_deals['Balance'][sell_index] = round(BALANCE, 2)

                    print(f" -> Final Sell at {last_price} | Profit: {profit_percent:.2f}%")
                    sell_index += 1

def save_results():
    global exchange_deals, BALANCE

    if len(exchange_deals['index']) <= 0:
        print("\n[INFO] No trades were made. No results to save.")
        return
    
    print("\n--- Trading Summary ---")

    final_df = pd.DataFrame(exchange_deals)
    print(final_df)

    if os.path.exists("quantum_bot_trading_summary.csv"):
        os.remove("quantum_bot_trading_summary.csv")

    final_df.to_csv("quantum_bot_trading_summary.csv", index=False)

    with open("quantum_bot_final_balance.txt", "w") as f:
        f.write(f"Final Balance: {BALANCE:.2f} USDT\n")
        f.write(f"Final profit/loss: {BALANCE - STARTING_MONEY:.2f} USDT\n ({((BALANCE - STARTING_MONEY) / STARTING_MONEY) * 100:.2f}%)\n")

    print("\n[INFO] Trading summary saved to 'quantum_bot_trading_summary.csv'")
    


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped manually by user.")
    finally:
        save_results()