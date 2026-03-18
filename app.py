import os
from flask import Flask, request, jsonify
import ccxt

app = Flask(app.py)


# --- BingX Setup ---
exchange = ccxt.bingx({
    'apiKey': os.getenv('BINGX_API_KEY'),
    'secret': os.getenv('BINGX_SECRET'),
    'options': {'defaultType': 'swap'} # Perpetuals
})

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data or data.get('passphrase') != os.getenv('WEBHOOK_PASSPHRASE'):
        return jsonify({"status": "unauthorized"}), 401

    # Format symbol for BingX (e.g., BTC-USDT)
    symbol = data.get('ticker').replace("USDT.P", "-USDT").replace("/", "-")
    action = data.get('action').lower() # 'buy' or 'sell'
    
    try:
        # 1. Fetch Balance & Price
        balance = exchange.fetch_balance()
        usdt_balance = balance['total']['USDT']
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # 2. Calculate Qty (10% of Balance)
        risk_percent = float(data.get('risk_percent', 10))
        position_value = usdt_balance * (risk_percent / 100)
        qty = position_value / price
        
        # 3. Open Market Order
        order = exchange.create_market_order(symbol, action, qty)
        print(f"Opened {action} for {symbol}")

        # 4. Set Stop Loss (1%)
        sl_percent = float(data.get('sl_percent', 1))
        sl_price = price * (1 - sl_percent/100 if action == 'buy' else 1 + sl_percent/100)
        exchange.create_order(symbol, 'STOP_MARKET', 'sell' if action == 'buy' else 'buy', qty, params={'stopPrice': sl_price})
        
        # 5. Set 3 Take Profits (Split qty into 3 parts)
        tp_levels = [data.get('tp1_percent'), data.get('tp2_percent'), data.get('tp3_percent')]
        tp_qty = qty / 3 # Simple 1/3 split
        
        for tp_p in tp_levels:
            multiplier = (1 + float(tp_p)/100) if action == 'buy' else (1 - float(tp_p)/100)
            tp_price = price * multiplier
            exchange.create_order(symbol, 'LIMIT', 'sell' if action == 'buy' else 'buy', tp_qty, tp_price)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
