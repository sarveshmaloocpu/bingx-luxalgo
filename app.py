import os
from flask import Flask, request, jsonify
import ccxt

app = Flask(__name__)

# --- BingX Configuration ---
# These are pulled from your Render Environment Variables
exchange = ccxt.bingx({
    'apiKey': os.getenv('BINGX_API_KEY'),
    'secret': os.getenv('BINGX_SECRET'),
    'options': {'defaultType': 'swap'}  # Set to 'swap' for Perpetual Futures
})

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    # 1. Security Check
    if not data or data.get('passphrase') != os.getenv('WEBHOOK_PASSPHRASE'):
        return jsonify({"status": "unauthorized", "message": "Invalid passphrase"}), 401

    # 2. Extract Data from TradingView
    # Formats symbol for BingX (e.g., BTC-USDT)
    symbol = data.get('ticker').replace("USDT.P", "-USDT").replace("/", "-")
    action = data.get('action').lower() # 'buy' or 'sell'
    
    try:
        # 3. Fetch Balance & Current Price
        balance = exchange.fetch_balance()
        usdt_balance = balance['total'].get('USDT', 0)
        
        ticker_info = exchange.fetch_ticker(symbol)
        price = ticker_info['last']
        
        # 4. Calculate Quantity (10% of Total USDT Balance)
        risk_percent = float(data.get('risk_percent', 10.0))
        position_value = usdt_balance * (risk_percent / 100)
        qty = position_value / price
        
        # 5. Open Market Position
        order = exchange.create_market_order(symbol, action, qty)
        print(f"Opened {action} for {symbol} at {price}")

        # 6. Set Stop Loss (1%)
        sl_percent = float(data.get('sl_percent', 1.0))
        sl_price = price * (1 - sl_percent/100 if action == 'buy' else 1 + sl_percent/100)
        
        # BingX Trigger for Stop Loss
        exchange.create_order(
            symbol=symbol, 
            type='STOP_MARKET', 
            side='sell' if action == 'buy' else 'buy', 
            amount=qty, 
            params={'stopPrice': sl_price}
        )
        
        # 7. Set 3 Take Profits (1.10%, 2.25%, 3.8%)
        # Splitting the position into 3 equal parts (33.3% each)
        tp_levels = [
            float(data.get('tp1_percent', 1.10)), 
            float(data.get('tp2_percent', 2.25)), 
            float(data.get('tp3_percent', 3.8))
        ]
        tp_qty = qty / 3
        
        for tp_p in tp_levels:
            multiplier = (1 + tp_p/100) if action == 'buy' else (1 - tp_p/100)
            tp_price = price * multiplier
            
            exchange.create_order(
                symbol=symbol, 
                type='LIMIT', 
                side='sell' if action == 'buy' else 'buy', 
                amount=tp_qty, 
                price=tp_price
            )

        return jsonify({"status": "success", "message": f"Executed {action} with SL & 3 TPs"}), 200

    except Exception as e:
        print(f"Execution Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Render uses the PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
