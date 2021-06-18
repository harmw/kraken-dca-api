import base64
import hashlib
import hmac
import json
import os
import requests
import time
import urllib

from fastapi import FastAPI
from . import config


api_key = os.getenv('API_KEY')
api_private_key = os.getenv('PRIVATE_KEY')
dca_config = config.Settings().dca_config
orderbook_path = './orderbook'

app = FastAPI()

USERREF = config.Settings().userref


def _call_kraken(endpoint, payload):
    api_nonce = str(int(time.time() * 1000))
    payload['nonce'] = api_nonce
    signature = _get_signature(endpoint, payload)
    headers = {'API-Key': api_key, 'API-Sign': signature, 'nonce': api_nonce, 'user-agent': 'dca-bot'}
    base_url = 'https://api.kraken.com'
    url = f'{base_url}{endpoint}'
    return requests.post(url, data=payload, headers=headers).json()


def _get_signature(endpoint, data):
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data['nonce']) + postdata).encode()
    message = endpoint.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(api_private_key), message, hashlib.sha512)
    sigdigest = base64.b64encode(mac.digest())
    return sigdigest.decode()


def get_balance():
    endpoint = '/0/private/Balance'
    payload = {}
    kraken = _call_kraken(endpoint, payload)
    if 'error' in kraken and len(kraken['error']) > 0:
        return kraken['error']
    for p in ['EOS', 'DASH', 'XXRP']:
        del kraken['result'][p]
    return kraken['result']


def get_ticker_data(pairs: list) -> list:
    """
    a: ask
    b: bid
    c: last closed transaction
    """
    endpoint = '/0/public/Ticker'
    payload = {
        'pair': ','.join(pairs)
    }
    kraken = _call_kraken(endpoint, payload)
    if 'error' in kraken and len(kraken['error']) > 0:
        print(kraken['error'])
        return []
    else:
        return kraken['result']


def add_order(pair: str, price: float, volume: float, i_am_just_testing: bool) -> bool:
    endpoint = '/0/private/AddOrder'
    payload = {
        'userref': USERREF,
        'ordertype': 'limit',
        'type': 'buy',
        'pair': pair,
        'price': str(price),
        'volume': volume
    }

    if i_am_just_testing:
        payload['validate'] = 'true'

    kraken = _call_kraken(endpoint, payload)
    if 'error' in kraken and len(kraken['error']) > 0:
        return kraken['error']
    else:
        return kraken['result']['descr']['order']


# @repeat_every(seconds=15)
# @app.on_event("startup")
# async def startup_event(): -> None


@app.get("/")
def read_root() -> dict:
    return {"message": "Hello Crypto"}


@app.get("/api/strategy/execute")
def api_strategy_execute(i_am_just_testing: bool = True) -> dict:
    trades = dca_config['trades']
    tickers_data = get_ticker_data(trades.keys())
    result = {}
    timestamp = str(int(time.time()))
    for pair in trades.keys():
        result[pair] = {}
        buying_power = trades[pair]['amount']
        if pair not in tickers_data:
            result[pair]['meta'] = f'{pair}: not found in ticker data'
            continue
        price = float(tickers_data[pair]['a'][0])
        volume = float(buying_power / price)

        result[pair]['task'] = f'invest {buying_power}: place order {volume} @ {price}'
        result[pair]['meta'] = {'test': True if i_am_just_testing else False}
        result[pair]['reply'] = add_order(pair, price, volume, i_am_just_testing)

        # To keep this lean, write a file reflecting order details instead of depending on something more mature like a
        # database.
        data = {}
        file_name = f'{orderbook_path}/{timestamp}-{pair}.json'
        with open(file_name, 'w+') as f:
            f.write(json.dumps(result))

        # Post something small to a private Slack channel
        pretty_volume = float(round(volume * 10000) / 10000)
        slack_data = {
            'blocks': [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f">:ledger: invest EUR {buying_power} in *{pair}*\n>:chart_with_upwards_trend: buy {pretty_volume} @ {price}"
                }
            }]
        }
        slack_url = config.Settings().slack_hook_dev if i_am_just_testing else config.Settings().slack_hook_main
        slack = requests.post(slack_url, json=slack_data)
        if not slack.ok:
            print(slack.text)
    return result


@app.get("/api/strategy/info")
def api_strategy() -> dict:
    return {'dca': dca_config}


@app.get("/api/balance")
def api_balance(slack: bool = False) -> dict:
    balance: dict = get_balance()
    trades = dca_config['trades']
    tickers_data = get_ticker_data(trades.keys())

    for pair in trades.keys():
        name = trades[pair]['name']
        amount = float(balance[name])
        value = float(tickers_data[pair]['a'][0]) * amount
        balance[name] = {'value': value, 'amount': amount}

    if slack:
        text = "*Balance*\n"
        del balance['ZEUR']
        for asset in balance.keys():
            amount = round(balance[asset]['amount'], 4)
            value = round(balance[asset]['value'], 2)
            text+= f":moneybag: {amount} *{asset}*: EUR {value}\n"
        slack_data = {
            'blocks': [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            }]
        }
        slack_url = config.Settings().slack_hook_main
        slack = requests.post(slack_url, json=slack_data)
        if not slack.ok:
            print(slack.text)
    return {'balance': balance}
