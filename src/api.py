import base64
import hashlib
import hmac
import os
import requests
import time
import urllib

from fastapi import FastAPI


api_key = os.getenv('API_KEY')
api_private_key = os.getenv('PRIVATE_KEY')

# This integer is used to label all orders coming from us
USERREF = 1337

app = FastAPI()

dca_config = {
    'interval': 'weekly',
    'trades': {
        'XXBTZEUR': {'amount': 12},
        'XETHZEUR': {'amount': 16},
        'XXMRZEUR': {'amount': 12},
        'ADAEUR': {'amount': 10}
    }
}


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
        logging.warning(kraken['error'])
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
    for pair in trades.keys():
        result[pair] = {}
        buying_power = trades[pair]['amount']
        if pair not in tickers_data:
            result[pair]['meta'] = f'{pair}: not found in ticker data'
            continue
        price = float(tickers_data[pair]['a'][0])
        volume = float(buying_power / price)
        suffix = " (test)" if i_am_just_testing else ""

        result[pair]['task'] = f'invest EUR {buying_power}: place order {volume} @ {price}{suffix}'
        result[pair]['reply'] = add_order(pair, price, volume, i_am_just_testing)
    return result


@app.get("/api/strategy/info")
def api_strategy() -> dict:
    return {'dca': dca_config}


@app.get("/api/balance")
def api_strategy() -> dict:
    return {'balance': get_balance()}
