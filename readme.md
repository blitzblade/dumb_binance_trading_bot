### ref

Binance api source: https://github.com/sammchardy/python-binance

### setup

Easy peasy!

I assume you've checked out the binance api repo... Right? Right?

If you didn't because you don't like reading like me, just [get the API key](https://www.binance.com/en/support/faq/360002502072) and secret from binance, plug it in `config.json` and try this out!

- Pip install the package in requirements.txt `pip install -r requirements.txt`
- Run the `trader.py` file

### configure

Set up the cryptos you'd like to trade in `config.json`. All percentages are in their decimal values. For instance, when you see 0.01, that's 1%

Choose which cryptos actually get traded by changing the list under `__main__` in `trader.py`

```python
cryptos = ["XLM", "BTC", "LTC", "ETH"]
# change that to what you want. These cryptos must have been setup in config.json
```
