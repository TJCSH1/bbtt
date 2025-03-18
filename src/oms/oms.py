# Standard library imports
from base64 import urlsafe_b64encode
from hashlib import sha256
from hmac import new
from json import dumps, loads
from threading import Event, Thread
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

# Third-party imports
from websocket import WebSocketApp

# Local imports
from ..utils.throttle import throttle
from ..utils.utils import get_key

# Maximum number of API calls per second
API_RATE: int = 10


class Oms:
    """
    A class to manage trading operations including orders and positions, and 
    real-time data on Bybit.

    This class provides methods for interacting with Bybit's WebSocket API to 
    manage active orders, track positions, and handle real-time data updates 
    for a specific symbol.

    Properties:
        active (bool): Indicates whether there are any active orders.
        active_orders (Dict[str, Dict[str, Any]]): A dictionary containing 
            active orders, keyed by order link ID.
        position (float): The signed position size for the tracked symbol, 
            where positive values represent long positions and negative values 
            represent short positions.
        side (str): The side of the last executed order.

    Methods:
        connect() -> None: Establishes the WebSocket connections to Bybit.
        create_order() -> None: Creates a new market or limit order on Bybit.
        amend_order() -> None: Edits an active limit order on Bybit.
        cancel_order() -> None: Cancels an active limit order on Bybit.
        cancel_all() -> None: Cancels all active limit orders on Bybit.
        order_status() -> str: Retrieves the current status of an active order.
        remove_status() -> None: Removes an order from the order status 
            dictionary.
        reconnect() -> None: Reconnects the WebSockets.
        kill() -> None: Closes all active WebSocket connections to Bybit.

    Example:
        # Creating an instance
        oms: Oms = Oms(
            symbol="BTCUSDT",
            category="linear",
            api_rate=10
        )
        oms.connect()

        # Placing an order
        oms.create_order(
            price="98000",
            qty="0.2",
            side="Buy",
            orderType="Limit",
            timeInForce="PostOnly",
            isLeverage=1,
            orderLinkId="UUID1234"
        )

        # Killing
        oms.kill()
    """
    def __init__(
        self, 
        symbol: str,
        category: str,
        api_rate: Optional[int]=10,
        mainnet_private: Optional[str]="wss://stream.bybit.com/v5/private",
        mainnet_trade: Optional[str]="wss://stream.bybit.com/v5/trade",
    ) -> None:
        """
        Initialize the order management system.

        Args:
            symbol (str): The trading pair symbol (e.g., "BTCUSDT").
            category (str): The category of the instrument (e.g., "linear").
            api_rate (Optional[int]): The API rate limit per second. Defaults 
                to 10 calls per second.
            mainnet_private (Optional[str]): The URL for Bybit's private API.
                Defaults to "wss://stream.bybit.com/v5/private".
            mainnet_trade (Optional[str]): The URL for Bybit's trading API.
                Defaults to "wss://stream.bybit.com/v5/trade".

        Returns:
            None
        """
        # Initializing
        global API_RATE
        API_RATE = api_rate
        self._symbol: str = symbol
        self._category: str = category
        self._position_event: Event = Event()
        self._websockets: Dict[str, WebSocketApp] = {}
        self._running: Dict[str, Thread] = {}
        self._flag: bool = True

        # Creating the UUID for the order link ID
        self._uuid: str = uuid4()
        self._uuid = urlsafe_b64encode(self._uuid.bytes).decode("utf-8")
        self._uuid = self._uuid.rstrip("=\n")[:10]
        self._order_link_id_n: int = 0
        self._order_status: Dict[str, str] = {}

        # URLs
        self._mainnet_private: str = mainnet_private
        self._mainnet_trade: str = mainnet_trade

        # Initializing class attributes
        self._active_orders: Dict[str, Dict[str, Any]] = {}
        self._position: float = 0.0
        self._side: str = None

        # Fast execution
        self._fe: str = f"execution.fast.{category}"

    def __getitem__(self, order_link_id: str) -> Dict[str, Any]:
        """
        Retrieves the active limit order associated with `order_link_id`. 

        If no active order is found, returns an empty dictionary.

        Returns:
            Dict[str, Any]: The active limit order if available, otherwise an 
                empty dictionary.
        """
        try:
            self._active_orders[order_link_id]
        except KeyError:
            return {}

    def _pinger(self, ws: WebSocketApp) -> None:
        """
        A pinger to keep the Bybit WebSocket connection alive.

        Args:
            ws (WebSocketApp): a Bybit WebSocket connection.

        Returns:
            None.
        """
        while self._flag:
            ws.send(dumps({"op": "ping"}))
            sleep(20)

    def _on_order_open(
        self,
        ws: WebSocketApp
    ) -> None:
        """
        on_open handler for the Bybit order WebSocket.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.

        Returns:
            None.
        """
        # Initializing
        print("Oms | Opening the Bybit order connection.")
        topic: str = "order"

        # Creating the signature
        expires: int = int((time()+10)*1000)
        val: str = f"GET/realtime{expires}"
        signature: str = str(
            new(
                bytes(
                    get_key("api_secret"), 
                    "utf-8"
                ),
                bytes(
                    val, 
                    "utf-8"
                ),
                digestmod=sha256
            ).hexdigest()
        )

        # Authorizing
        ws.send(
            dumps(
                {
                    "op": "auth",
                    "args": [
                        get_key(key="api_key"),
                        expires,
                        signature
                    ]
                }
            )
        )

        # Subscribing to order stream
        ws.send(
            dumps(
                {
                    "op": "subscribe",
                    "args": [topic]
                }
            )
        )

        # Pinger
        ping: Thread = Thread(
            target=self._pinger, 
            args=(ws,), 
            daemon=True
        )
        ping.start()

    def _on_exec_open(
        self,
        ws: WebSocketApp
    ) -> None:
        """
        on_open handler for the Bybit fast execution WebSocket.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.

        Returns:
            None.
        """
        # Initializing
        print(f"Oms | Opening the Bybit {self._fe} connection.")

        # Creating the signature
        expires: int = int((time()+10)*1000)
        val: str = f"GET/realtime{expires}"
        signature: str = str(
            new(
                bytes(
                    get_key("api_secret"), 
                    "utf-8"
                ),
                bytes(
                    val, 
                    "utf-8"
                ),
                digestmod=sha256
            ).hexdigest()
        )

        # Authorizing
        ws.send(
            dumps(
                {
                    "op": "auth",
                    "args": [
                        get_key(key="api_key"),
                        expires,
                        signature
                    ]
                }
            )
        )

        # Subscribing to fast execution stream
        ws.send(
            dumps(
                {
                    "op": "subscribe",
                    "args": [self._fe]
                }
            )
        )

        # Pinger
        ping: Thread = Thread(
            target=self._pinger, 
            args=(ws,), 
            daemon=True
        )
        ping.start()

    def _on_trade_open(
        self,
        ws: WebSocketApp
    ) -> None:
        """
        on_open handler for the Bybit trade WebSocket.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.

        Returns:
            None.
        """
        # Initializing
        print("Oms | Opening the Bybit trade connection.")

        # Creating the signature
        expires: int = int((time()+10)*1000)
        val: str = f"GET/realtime{expires}"
        signature: str = str(
            new(
                bytes(
                    get_key("api_secret"), 
                    "utf-8"
                ),
                bytes(
                    val, 
                    "utf-8"
                ),
                digestmod=sha256
            ).hexdigest()
        )

        # Authorizing
        ws.send(
            dumps(
                {
                    "op": "auth",
                    "args": [
                        get_key(key="api_key"),
                        expires,
                        signature
                    ]
                }
            )
        )

        # Pinger
        ping: Thread = Thread(
            target=self._pinger, 
            args=(ws,), 
            daemon=True
        )
        ping.start()

    def _on_order_message(
        self,
        ws: WebSocketApp,
        msg: str
    ) -> None:
        """
        Handles incoming WebSocket messages for this class, processing orders
        based on the associated symbol and category.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.
            msg (str): A Bybit WebSocket order message.

        Returns:
            None.
        """
        msg: Dict[str, Any] = loads(msg)
        try:
            if msg["topic"] == "order":
                # Checking if any orders
                if any(
                    o["symbol"] == self._symbol and
                    o["category"] == self._category for
                    o in msg["data"]
                ):
                    # Unpacking the orders and sorting
                    data: List[Dict[str, Any]] = sorted(
                        (
                            o for o in msg["data"] if
                            o["symbol"] == self._symbol and
                            o["category"] == self._category
                        ),
                        key=lambda o: int(o["updatedTime"])
                    )

                    # Processing the orders
                    for o in data:
                        self._order_status[o["orderLinkId"]] = o["orderStatus"]
                        if float(o["leavesQty"]) != 0:
                            self._active_orders[o["orderLinkId"]] = o
                        else:
                            self._active_orders.pop(
                                o["orderLinkId"], 
                                None
                            )
        except Exception:
            if "success" in msg.keys():
                if not msg["success"]:
                    raise ConnectionError("order websocket not connected.")

    def _on_exec_message(
        self,
        ws: WebSocketApp,
        msg: str
    ) -> None:
        """
        Handles incoming WebSocket messages for this class, processing 
        executions based on the associated symbol and category.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.
            msg (str): A Bybit WebSocket fast execution message.

        Returns:
            None.
        """
        msg: Dict[str, Any] = loads(msg)
        try:
            if (
                msg["topic"] == self._fe and
                any(
                    e["symbol"] == self._symbol and
                    e["category"] == self._category for
                    e in msg["data"]
                )
            ):
                # Setting the event
                self._position_event.set()

                # Sorting the message
                data: List[Dict[str, Any]] = sorted(
                    (
                        e for e in msg["data"] if
                        e["symbol"] == self._symbol and
                        e["category"] == self._category
                    ),
                    key=lambda e: int(e["execTime"])
                )

                # Processing executions
                for e in data:
                    self._position += (
                        float(e["execQty"]) if
                        e["side"] == "Buy" else
                        -float(e["execQty"])

                    )

                # Setting the side attribute
                self._side = data[-1]["side"]

                # Clearing the event
                self._position_event.clear()
        except KeyError:
            if "success" in msg.keys():
                if not msg["success"]:
                    raise ConnectionError(
                        f"{self._fe} websocket not connected."
                    )

    def _on_trade_message(
        self,
        ws: WebSocketApp,
        msg: str
    ) -> None:
        """
        Handles incoming WebSocket messages for this class, processing trades.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.
            msg (str): A Bybit WebSocket trade message.

        Returns:
            None.
        """
        msg: Dict[str, Any] = loads(msg)
        if msg["retCode"] != 0:
            raise ConnectionError(f"retCode error: {msg['retCode']}")

    @property
    def active(self) -> bool:
        """
        Returns True if there are active orders, else False.
        """
        return bool(self._active_orders)

    @property
    def active_orders(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns the dictionary of active orders.
        """
        return self._active_orders

    @property
    def position(self) -> float:
        """
        Returns the signed inventory position.
        """
        return self._position

    @property
    def side(self) -> str:
        """
        Returns the side of the last executed order.
        """
        return self._side

    @throttle(rate=API_RATE)
    def connect(self) -> None:
        """
        Connects to Bybit's order stream, position stream and trade stream.

        Return:
            None.
        """
        # Defining the on_error handler
        def on_error(
            ws: WebSocketApp, 
            exc: BaseException
        ) -> None:
            print(f"Error encountered: {exc}")

        # Defining the on_close handler
        def on_close(topic: str) -> Callable:
            def closer(
                ws: WebSocketApp,
                close_status_code: int,
                close_reason: str
            ) -> None:
                print(f"Oms | Bybit {topic} connection closed.")
            return closer

        # Creating the order WebSocket
        self._websockets["order"] = WebSocketApp(
            self._mainnet_private,
            on_message=self._on_order_message,
            on_error=on_error,
            on_open=self._on_order_open,
            on_close=on_close(topic="order")
        )

        # Creating the fast execution WebSocket
        self._websockets[self._fe] = WebSocketApp(
            self._mainnet_private,
            on_message=self._on_exec_message,
            on_error=on_error,
            on_open=self._on_exec_open,
            on_close=on_close(topic=self._fe)
        )

        # Creating the trade WebSocket
        self._websockets["trade"] = WebSocketApp(
            self._mainnet_trade,
            on_message=self._on_trade_message,
            on_error=on_error,
            on_open=self._on_trade_open,
            on_close=on_close(topic="trade")
        )

        # Running the WebSockets
        self._running = {}
        for key, value in self._websockets.items():
            self._running[key] = Thread(
                target=lambda ws: ws.run_forever(),
                args=(value,),
                daemon=True
            )
            self._running[key].start()
        
        # Sleeping
        sleep(1)

    @throttle(rate=API_RATE)
    def create_order(self, **kwargs: Dict[str,Any]) -> None:
        """
        Creates a market or limit order on Bybit.

        Args:
            **kwargs (Dict[str, Any]): Order parameters (EXCLUDING category 
                and symbol). See Bybit API documentation for available options:
                https://bybit-exchange.github.io/docs/v5/order/create-order.

        Returns:
            None.
        """
        # Generating the args
        args: Dict[str, Any] = {
            "symbol": self._symbol,
            "category": self._category,
        }
        args.update(dict(kwargs))
        if "orderLinkId" not in args:
            args["orderLinkId"] = f"{self._uuid}-{self._order_link_id_n}"
            self._order_link_id_n += 1
        self._order_status[args["orderLinkId"]] = ""

        # Checking if the position is being updated
        if not self._position_event.is_set():
            # Sending the order
            order: Dict[str, Any] = {
                "header": {
                    "X-BAPI-TIMESTAMP": str(int(time()*1000)),
                    "X-BAPI-RECV-WINDOW": "8000"
                },
                "op": "order.create",
                "args": [args]
            }
            self._websockets["trade"].send(dumps(order))

            # Updating status if qty is zero
            if float(args["qty"]) == 0:
                self._order_status[args["orderLinkId"]] = "Unsubmitted"
        else:
            # Updating the status of the unsubmitted order
            self._order_status[args["orderLinkId"]] = "Unsubmitted"

    @throttle(rate=API_RATE)
    def amend_order(self, **kwargs: Dict[str, Any]) -> None:
        """
        Amends an active limit order on Bybit.

        Args:
            **kwargs (Dict[str, Any]): Order parameters (EXCLUDING category 
                and symbol). See Bybit API documentation for available options:
                https://bybit-exchange.github.io/docs/v5/order/create-order.

        Returns:
            None.
        """
        # Generating the args
        args: Dict[str, Any] = {
            "symbol": self._symbol,
            "category": self._category,
        }
        args.update(dict(kwargs))

        # Creating the order
        order: Dict[str, Any] = {
            "header": {
                "X-BAPI-TIMESTAMP": str(int(time()*1000)),
                "X-BAPI-RECV-WINDOW": "8000"
            },
            "op": "order.amend",
            "args": [args]
        }

        # Sending the order
        self._websockets["trade"].send(dumps(order))

        # Updating status if qty is zero
        if float(args["qty"]) == 0:
            self._order_status[args["orderLinkId"]] = "Unsubmitted"

    @throttle(rate=API_RATE)
    def cancel_order(self, order_link_id: str) -> None:
        """
        Cancels an active limit order using its unique order link ID.

        Args:
            order_link_id (str): The unique identifier of the order.
        
        Returns:
            None.
        """
        # Creating the order
        try:
            orderId: str = self._active_orders[order_link_id]["orderId"]
            order: Dict[str, Any] = {
                "header": {
                    "X-BAPI-TIMESTAMP": str(int(time()*1000)),
                    "X-BAPI-RECV-WINDOW": "8000"
                },
                "op": "order.cancel",
                "args": [
                    {
                        "category": "linear",
                        "symbol": "ADAUSDT",
                        "orderId": orderId
                    }
                ]
            }

            # Sending the order
            self._websockets["trade"].send(dumps(order))
        except KeyError:
            pass

    def cancel_all(self) -> None:
        """
        Cancels ALL active limit orders.

        Returns:
            None.
        """
        # Cancelling all active limit orders
        keys: List[str] = list(self._active_orders.keys())
        for order_link_id in keys:
            self.cancel_order(
                order_link_id=order_link_id
            )

    def order_status(self, order_link_id: str) -> str:
        """
        Retrieves the status of an order based on its unique order link ID.

        Args:
            order_link_id (str): The unique identifier of the order.

        Returns:
            str: The current status of the order, which can be one of the
                following:
                    [
                        "",
                        "Unsubmitted",
                        "New",
                        "Cancelled",
                        "PartiallyFilled",
                        "Filled"
                    ].
        """
        return self._order_status[order_link_id]

    def remove_status(self, order_link_id: str) -> None:
        """
        Removes the entry associated with the given order link ID.

        Args:
            order_link_id (str): The unique identifier for the order.

        Returns:
            None.
        """
        self._order_status.pop(order_link_id, None)

    def reconnect(self) -> None:
        """
        Reconnects the WebSockets.

        Returns:
            None.
        """
        # Killing the websockets
        self.kill()
        sleep(1)

        # Reconnecting
        self.connect()

    def kill(self) -> None:
        """
        Kills ALL active WebSockets.

        Returns:
            None.
        """
        # Killing active connections
        self._flag = False
        sleep(1)
        if self._websockets:
            try:
                for key in self._websockets.keys():
                    self._websockets[key].close()
            except Exception:
                pass
        self._websockets = {}
