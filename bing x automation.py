import os
from flask import Flask, request, jsonify
import ccxt

app = Flask(__name__)

# --- BingX Configuration (Environment Variables) ---
exchange = ccxt.bingx({
    'apiKey': os.getenv('bnbVbCvTM5CvJewjARCWjRc55XlAQpWA9qxWmfch09Sfodaz5pyuHR63ODoDIEYiq8cZJNgTJCZbgy5P5BA'),
    'secret': os.getenv('l0wKvNeudGiQPVn9m6MS4qm95xFRMRW99Ynt9kzLIoJQvuADwzYmFkKJi1KywFgoQlcLnHG38uLC81DK3yg'),
    'options': {'defaultType': 'swap'} # 'swap' for BingX Perpetual Futures
})

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data or data.get('passphrase') != os.getenv('WEBHOOK_PASSPHRASE'):
        return jsonify({"status": "unauthorized"}), 401

    # BingX usually expects symbols like "BTC-USDT"
    symbol = data.get('ticker').replace("/", "-")
    side = 'buy' if data.get('action') == 'buy' else 'sell'
    
    try:
        # 1. Fetch Balance & Price
        balance = exchange.fetch_balance()
        usdt_balance = balance['total']['USDT']
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # 2. Calculate Position Size (10% of Balance)
        position_value = usdt_balance * (data.get('risk_percent') / 100)
        qty = position_value / price
        
        # 3. Open Market Position
        # Note: BingX requires 'side' (buy/sell) and 'amount' (qty)
        order = exchange.create_market_order(symbol, side, qty)
        
        # 4. Set Stop Loss (1%)
        sl_price = price * (0.99 if side == 'buy' else 1.01)
        # BingX Trigger Price for SL
        exchange.create_order(symbol, 'STOP_MARKET', 'sell' if side == 'buy' else 'buy', qty, params={'stopPrice': sl_price})
        
        # 5. Set 3 Take Profits (Split into 33%, 33%, 34%)
        tp_levels = [data.get('tp1_percent'), data.get('tp2_percent'), data.get('tp3_percent')]
        tp_qty = [qty * 0.33, qty * 0.33, qty * 0.34]
        
        for i in range(3):
            multiplier = (1 + tp_levels[i]/100) if side == 'buy' else (1 - tp_levels[i]/100)
            tp_price = price * multiplier
            exchange.create_order(symbol, 'LIMIT', 'sell' if side == 'buy' else 'buy', tp_qty[i], tp_price)

        return jsonify({"status": "success", "msg": f"BingX {side} executed with SL & 3 TPs"}), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
