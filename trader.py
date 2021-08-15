from binance.client import Client
from binance.websockets import BinanceSocketManager
import time
import pickle
import os, sys
import json
import threading

def load_config():
    return json.load(open("config.json"))

def print_err(err):
    print(str(err) + " on line " + str(sys.exc_info()[2].tb_lineno))

config = load_config()

api_key = config["API_KEY"]
api_secret = config["API_SECRET"]
api_url = config["API_URL"]

SYMBOL = "XLMUSDT"
CRYPTO = "XLM"
FIAT = "USDT"

BUY_PERCENTAGE = 0.1 #10%
BUY_PRICE_PERCENTAGE = 0.01 #1%
MINIMUM_BUY_USD_VALUE = 10
SELL_PERCENTAGE = 0.1 #10%
SELL_PRICE_PERCENTAGE = 0.01 #1%
MINIMUM_BUY_USD_VALUE = 10
MINIMUM_SELL_USD_VALUE = 10
MINIMUM_NOTION = 11 #qty * price
MINIMUM_CRYPTO_BALANCE = 0.5 #50% of initial balance
MINIMUM_FIAT_BALANCE = 0.5 #50% of initial balance
MAX_NUMBER_OF_ORDERS = 2
MAX_BUY_SELL_DIFFERENCE = 2

data = {
    "current_price": 0,
    "selling_price": 0,
    "buying_price": 0,
    "prv_selling_price": 0,
    "prv_buying_price": 0,
    "crypto_balance": 0,
    "fiat_balance": 0
}

client = Client(api_key, api_secret)

info = client.get_symbol_info(SYMBOL)
print(info)


class Crypto():
    def __init__(self, client, crypto):
        self.config = config["CRYPTOS"][crypto]
        self.client = client
        self.symbol = self.config["SYMBOL"]
        self.crypto = crypto
        self.fiat = self.config["FIAT"]
    
    def price(self):
        avg_price = self.client.get_avg_price(symbol=self.symbol)
        return float(avg_price["price"])

    def balance(self, asset):
        asset = self.client.get_asset_balance(asset=asset)
        print("asset: ", asset)
        return float(asset["free"])
    
    def crypto_balance(self):
        return self.balance(self.crypto)
    
    def fiat_balance(self):
        return self.balance(self.fiat)

    def usd_price(self):
        return self.usd_value(self.price(), self.crypto_balance())
    
    def usd_value(self, price, qty):
        return price * qty
    
    def crypto_value(self, price, usd):
        return usd / price

    def get_open_orders(self):
        orders = self.client.get_open_orders(symbol=self.symbol)
        return [{
            "side": i["side"], 
            "status": i["status"], 
            "price": i["price"],
            "time": i["time"],
            "order_id": i["orderId"]
         } for i in orders]

    def get_orders(self):
        orders = self.client.get_all_orders(symbol=self.symbol, recvWindow=1000*59)
        return [{
            "side": i["side"], 
            "status": i["status"], 
            "price": i["price"],
            "time": i["time"],
            "order_id": i["orderId"]
         } for i in orders]

    
class Trader():

    def __init__(self, crypto, data):
        self.crypto = crypto
        self.config = crypto.config
        
        d = self.load_data()
        self.data = data if d == None else d
        initial_price = self.crypto.price()
        
        self.data["current_price"] = initial_price
        self.data["crypto_balance"] = self.crypto.crypto_balance()
        self.data["fiat_balance"] = self.crypto.fiat_balance()
        self.data["buying_price"] = initial_price
        self.data["selling_price"] = initial_price
        self.data["prv_buying_price"] = initial_price
        self.data["prv_selling_price"] = initial_price
        self.data["buy_sell_difference"] = 0

    
    def buy(self, qty=None):

        orders = self.crypto.get_orders()

        pending_buy_orders = [i for i in orders if i["side"] == "BUY" and i["status"] == "NEW"]
        print("PENDING buy ORDERS: ", pending_buy_orders)

        fiat_balance = self.crypto.fiat_balance()
        print("FIAT BALANCE: ", fiat_balance)
        print("BUY SELL DIFFERENCE: ", self.data["buy_sell_difference"])
        if len(pending_buy_orders) < self.config["MAX_NUMBER_OF_ORDERS"] and \
            fiat_balance > self.data['fiat_balance'] * self.config["MINIMUM_FIAT_BALANCE"] and\
                self.data["buy_sell_difference"] < self.config["MAX_BUY_SELL_DIFFERENCE"] and \
                    fiat_balance > self.config["MINIMUM_FIAT_BALANCE_VALUE"]: #place new order
            print("PLACING NEW BUY ORDER...")
            price = None
            current_price = self.crypto.price()
            old_price = self.data["prv_buying_price"]

            if old_price < current_price and old_price >= (current_price - 0.05 * current_price):
                current_price = old_price

            price = current_price - current_price * self.config["BUY_PRICE_PERCENTAGE"]
            
            qty_usd = self.crypto.fiat_balance() * self.config["BUY_PERCENTAGE"] #in dollars
            qty = self.crypto.crypto_value(price, qty_usd)
            if qty < self.crypto.crypto_value(price, self.config["MINIMUM_BUY_USD_VALUE"]):
                qty =  self.crypto.crypto_value(price, self.config["MINIMUM_BUY_USD_VALUE"])

            if qty * price < self.config["MINIMUM_NOTION"]:
                qty = self.config["MINIMUM_NOTION"] / price
            
            print("BUY SUMMARY:")
            price = round(price, self.config["PRICE_PRECISION"])
            print("PRICE: ", price)
            qty = round(qty, self.config["QTY_PRECISION"])
            print("QTY: ", qty)
            order = client.create_order( #use client.create_order
            symbol=self.crypto.symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_LIMIT,
            price=price,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=qty
            )

            self.data["prv_buying_price"] = current_price
            self.data["buy_sell_difference"] += 1
            
            print("ORDER CREATED: ", order)
        self.save_data()
    
    def remove_old_orders(self, orders, age=1):
        for i in orders:
            order_age = float(i["time"]) / 1000
            print("REMOVING OLD ORDERS: ")
            print("TIME FOR ORDER: ", order_age)
            print("RIGHT NOW: ", time.time())
            if time.time() - age*60*60 > order_age:
                print("ORDER TAKING TOO LONG... REMOVING")
                self.cancel_order(i)
            else:
                print("NOT OLD ENOUGH")

    def sell(self, qty=None):
        # place a test market buy order, to place an actual order use the create_order function
        
        orders = self.crypto.get_orders()
        pending_sell_orders = [i for i in orders if i["side"] == "SELL" and i["status"] == "NEW"]
        

        print("PENDING sell ORDERS: ", pending_sell_orders)

        crypto_balance = self.crypto.crypto_balance()
        print("CRYPTO BALANCE: ", crypto_balance)
        print("BUY SELL DIFFERENCE: ", self.data["buy_sell_difference"])

        if len(pending_sell_orders) < self.config["MAX_NUMBER_OF_ORDERS"] and \
            crypto_balance > self.data['crypto_balance'] * self.config["MINIMUM_CRYPTO_BALANCE"] and\
                self.data["buy_sell_difference"] > -1 * self.config["MAX_BUY_SELL_DIFFERENCE"] and \
                    self.crypto.usd_price() > self.config["MINIMUM_CRYPTO_BALANCE_VALUE"]: #place new order
            print("PLACING NEW SELL ORDER...")
            price = None
            current_price = self.crypto.price()

            old_price = self.data["prv_selling_price"]

            if old_price > current_price and old_price <= (current_price + 0.05 * current_price):
                current_price = old_price

            price = current_price + current_price * self.config["SELL_PRICE_PERCENTAGE"]
            # old_sell_price = self.data["prv_selling_price"] + self.data["prv_selling_price"] * SELL_PRICE_PERCENTAGE

            # if sell_price > old_sell_price:
            #     price = sell_price
            # else:
            #     price = old_sell_price

            qty = self.crypto.crypto_balance() * self.config["SELL_PERCENTAGE"]
            if qty < self.crypto.crypto_value(price, self.config["MINIMUM_SELL_USD_VALUE"]):
                qty = self.crypto.crypto_value(price, self.config["MINIMUM_SELL_USD_VALUE"])

            if qty * price < self.config["MINIMUM_NOTION"]:
                qty = self.config["MINIMUM_NOTION"] / price
            
            print("SELL SUMMARY:")
            price = round(price, self.config["PRICE_PRECISION"])
            print("PRICE: ", price)
            qty = round(qty, self.config["QTY_PRECISION"])
            print("QTY: ", qty)
            order = client.create_order( #use client.create_order
            symbol=self.crypto.symbol,
            side=Client.SIDE_SELL,
            type=Client.ORDER_TYPE_LIMIT,
            price=price,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=qty
            )

            self.data["prv_selling_price"] = current_price
            self.data["buy_sell_difference"] -= 1
            
            print("ORDER CREATED: ", order)
        self.save_data()
    
    def cancel_open_orders(self, _type="ALL"):
        orders = self.crypto.get_open_orders()
        if _type == "SELL":
            orders = [order for order in orders if order["side"] == "SELL"]
        elif _type == "BUY":
            orders = [order for order in orders if order["side"] == "BUY"]

        for order in orders:
            self.cancel_order(order)
            
    def cancel_order(self, order):
        result = client.cancel_order(
                                symbol=self.crypto.symbol,
                                orderId=order["order_id"])
        count = 1 if order["side"] == "BUY" else -1

        self.data["buy_sell_difference"] += count 
        print("ORDER CANCELED: ", result)


    def trade(self):
        #run every hour
        #remove old orders if they're still there
        #place buy and sell orders
        print("="*30)
        print(" =====  ",self.crypto.crypto, "  ======")
        print("="*30)
        wait_minutes = 60
        number_of_times = 0
        number_of_times_in_a_day = (24*60) / wait_minutes
 
        while True:
            try:
                # if number_of_times % number_of_times_in_a_day == 0 and number_of_times > 0:
                #     self.cancel_open_orders()
                self.buy()
                self.sell()
                print("WAITING TO EXECUTE AGAIN...")
                time.sleep(wait_minutes*60)
                number_of_times += 1
            except Exception as ex:
                print_err(ex)
                time.sleep(wait_minutes*60)
    
    def save_data(self):
        with open(f"{self.crypto.crypto}_data.pkl","wb") as f:
            pickle.dump(self.data, f)
    
    def load_data(self):
        filename = f"{self.crypto.crypto}_data.pkl"
        if not os.path.exists(filename):
            f = open(filename, "wb")
            f.close()
            return None
        elif os.path.getsize(filename) <= 0:
            return None
        with open(filename, "rb") as f:        
            unpickler = pickle.Unpickler(f)
            return unpickler.load()
        
if __name__ == "__main__":
    cryptos = ["XLM", "BTC", "LTC", "ETH"]

    for c in cryptos:
        if config["CRYPTOS"].get(c) != None:
            crypto = Crypto(client=client, crypto=c)
            trader = Trader(crypto, data)
            t = threading.Thread(target=trader.trade)
            t.start()
