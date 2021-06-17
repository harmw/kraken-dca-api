from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Kraken DCA API"
    userref: int = 1337
    dca_config = {
        'interval': 'biweekly',
        'trades': {
            'XXBTZEUR': {'amount': 12},
            'XETHZEUR': {'amount': 16},
            'XXMRZEUR': {'amount': 12},
            'ALGOEUR': {'amount': 10}
        }
    }
