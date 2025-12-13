# 🧠 Quantum AI Trading Bot (BETA)

> **⚠️ IMPORTANT WARNING:** This project is currently in the **BETA** phase (testing).
> The AI model has been trained and optimized **exclusively for Bitcoin (BTC/USDT)**.
> This software is for educational purposes only and does not constitute financial advice. Use at your own risk.

## 📋 Overview
**Quantum Brain** is an autonomous cryptocurrency trading bot powered by Machine Learning (**XGBoost**).
The bot analyzes the market in real-time, calculates advanced technical indicators, and makes trading decisions based on statistical probability.

It is designed for **Swing Trading** on the **1-Hour (1H)** timeframe, aiming to capture significant market movements while filtering out noise.

## 🚀 Key Features
* **AI-Powered Logic:** Uses a Multi-Class XGBoost model to classify market conditions (Long, Short, or Hold).
* **Long & Short Strategy:** Capable of profiting from both rising and falling markets.
* **Smart Risk Management:** Built-in Take Profit (2.5%) and Stop Loss (1.5%) mechanisms.
* **Paper Trading Mode:** Runs a full real-time simulation using virtual balance (no real money risk).
* **Automated Journaling:** Saves every trade entry and exit to a CSV file for performance analysis.
* **Graceful Shutdown:** Handles `CTRL+C` safely by closing open positions and saving data before exiting.

## 📊 Strategy Configuration
* **Asset:** BTC/USDT
* **Timeframe:** 1 Hour (1H)
* **Target Profit:** 2.5%
* **Stop Loss:** 1.5%
* **Entry Logic:** The bot enters a trade only when the AI confidence score exceeds the dynamic threshold and confirms the trend direction.

## 🛠️ Prerequisites
The bot is built with Python 3. You need to install the following dependencies:

```bash
pip install ccxt pandas numpy xgboost scikit-learn joblib ta
```

## ⚙️ How to Run
**Step 1: Train the Model**
Before running the live bot, you must train the AI "Brain" using historical data:
```
python train_model.py
```
This will generate the quantum_model.pkl model file.

**Step 2: Run the Live Bot**
Start the bot in Paper Trading mode:
```
python quantum_ai_bot.py
```
The bot will start printing real-time logs. To stop the bot and close any open positions immediately, press CTRL+C.

## 📝 Trade Logs
All trading activity is automatically documented in quantum_trades_log.csv. The log format includes:
| Entry Time       | Type  | Entry Price | Exit Price | PnL (%) | Reason      | Balance |
| :---             | :---: | :---        | :---       | :---:   | :---        | ---:    |
| 2025-05-10 10:00 | SHORT | 62,500      | 60,937     | 2.50%   | TAKE PROFIT | 1002.50 |
| 2025-05-11 08:15 | LONG  | 61,000      | 60,085     | -1.50%  | STOP LOSS   | 1001.00 |
