import json
import os
from pathlib import Path
from kiteconnect import KiteConnect
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)
TOKEN_FILE = Path(".kite_token.json")


class KiteClient:
    def __init__(self):
        self.kite = KiteConnect(api_key=settings.kite_api_key)
        self._access_token: str | None = None
        self._load_token()

    def _load_token(self):
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
                token = data.get("access_token", "")
                if token:
                    self._access_token = token
                    self.kite.set_access_token(token)
                    logger.info("Loaded Kite access token from file")
            except Exception as e:
                logger.warning(f"Could not load saved token: {e}")

        if settings.kite_access_token:
            self._access_token = settings.kite_access_token
            self.kite.set_access_token(settings.kite_access_token)

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def generate_session(self, request_token: str) -> str:
        data = self.kite.generate_session(
            request_token, api_secret=settings.kite_api_secret
        )
        self._access_token = data["access_token"]
        self.kite.set_access_token(self._access_token)
        TOKEN_FILE.write_text(json.dumps({"access_token": self._access_token}))
        logger.info("Kite session generated and token saved")
        return self._access_token

    def is_authenticated(self) -> bool:
        if not self._access_token:
            return False
        try:
            self.kite.profile()
            return True
        except Exception:
            return False

    def get_quote(self, instruments: list[str]) -> dict:
        return self.kite.quote(instruments)

    def get_ohlc(self, instruments: list[str]) -> dict:
        return self.kite.ohlc(instruments)

    def get_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str = "5minute",
    ) -> list[dict]:
        return self.kite.historical_data(
            instrument_token, from_date, to_date, interval
        )

    def get_instruments(self, exchange: str = "NSE") -> list[dict]:
        return self.kite.instruments(exchange)

    def get_positions(self) -> dict:
        return self.kite.positions()

    def get_holdings(self) -> list[dict]:
        return self.kite.holdings()

    def get_orders(self) -> list[dict]:
        return self.kite.orders()

    def get_margins(self) -> dict:
        return self.kite.margins()

    def place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: float = 0,
        trigger_price: float = 0,
        tag: str = "ARC_BOT",
    ) -> str:
        return self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=product,
            order_type=order_type,
            price=price if price else None,
            trigger_price=trigger_price if trigger_price else None,
            tag=tag,
        )

    def cancel_order(self, order_id: str) -> str:
        return self.kite.cancel_order(
            variety=self.kite.VARIETY_REGULAR, order_id=order_id
        )

    def get_ltp(self, instruments: list[str]) -> dict:
        return self.kite.ltp(instruments)

    def get_option_chain(self, underlying: str = "NSE:NIFTY 50") -> dict:
        return self.kite.quote([underlying])

    @property
    def TRANSACTION_BUY(self):
        return self.kite.TRANSACTION_TYPE_BUY

    @property
    def TRANSACTION_SELL(self):
        return self.kite.TRANSACTION_TYPE_SELL

    @property
    def EXCHANGE_NSE(self):
        return self.kite.EXCHANGE_NSE

    @property
    def EXCHANGE_NFO(self):
        return self.kite.EXCHANGE_NFO


kite_client = KiteClient()
