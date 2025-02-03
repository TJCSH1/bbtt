# Standard library imports
from hashlib import sha256
from hmac import new
from json import dumps, loads
from threading import Thread
from time import sleep, time
from typing import Any, Callable, Dict, Optional

# Third-party imports
from websocket import WebSocketApp

# Local imports
from ..utils.utils import get_key


class SessionAcc:
    """
    A class for tracking FIFO (First In, First Out) accounting of executions 
    net of transaction costs (maker and taker fees) over Bybit's fast 
    execution WebSocket stream.

    The accounting is filtered based on a specified trading symbol and 
    category (e.g., spot, linear, inverse).

    Features:
        - Tracks profits and losses (PnL) with transaction cost deductions.
        - Computes session drawdown and maintains peak PnL.
        - Connects to and maintains a live WebSocket stream to receive 
          fast execution data.
        - Allows killing all active WebSocket connections.

    Attributes:
        pnl (float): Current net profit or loss for the session.
        max_pnl (float): Maximum net profit recorded during the session.
        drawdown (float): Maximum drawdown (PnL peak-to-trough loss).
        win_rate (float): The win rate of the closed positions, where a win is
            defined as a closed position with a non-negative net profit.

    Methods:
        connect (None): Establishes and subscribes to Bybit's fast execution 
            WebSocket stream for the specified trading symbol and category.
        kill (None): Terminates all active WebSocket connections.
        summary (None): Prints the profit (loss), maximum profit and maximum 
            drawdown to the console.

    Example:
        # Connecting
        session: SessionAcc = SessionAcc(
            symbol="BTCUSDT", 
            category="linear", 
            maker=0.02/100, 
            taker=0.055/100
        )
        session.connect()

        # Monitor PnL and drawdown during the session
        print(session.pnl, session.drawdown)

        # Terminating the WebSocket connection
        session.kill()
    """
    def __init__(
        self,
        symbol: str,
        category: str,
        maker: float,
        taker: float,
        mainnet_private: Optional[str]="wss://stream.bybit.com/v5/private"
    ) -> None:
        """
        Initializes the SessionAcc class with parameters for tracking FIFO 
        executions and calculating net profits (PnL) with transaction costs.

        Args:
            symbol (str): The trading pair symbol (e.g., 'BTCUSDT').
            category (str): The trading category ('spot', 'linear', or 
                'inverse').
            maker (float): Maker fee rate.
            taker (float): Taker fee rate.
            mainnet_private (Optional[str]): The WebSocket private endpoint URL 
                for Bybit. Defaults to "wss://stream.bybit.com/v5/private".
        
        Returns:
            None
        """
        # Initializing
        self._symbol: str = symbol
        self._category: str = category
        self._maker: float = maker
        self._taker: float = taker
        self._mainnet_private: str = mainnet_private
        self._websockets: Dict[str, WebSocketApp] = {}
        self._running: Dict[str, Thread] = {}
        self._buys: List[Dict[str, Any]] = []
        self._sells: List[Dict[str, Any]] = []
        self._wins: int = 0
        self._n_matched: int = 0
        self._topic: str = f"execution.fast.{category}"
        self._flag: bool = True

        # Attributes
        self._pnl: float = 0.0
        self._max_pnl: float = 0.0
        self._drawdown: float = 0.0

    @property
    def drawdown(self) -> float:
        """
        The session maximum drawdown.
        """
        return self._drawdown

    @property
    def max_pnl(self) -> float:
        """
        The session maximum net profit (loss).
        """
        return self._max_pnl

    @property
    def pnl(self) -> float:
        """
        The session net profit (loss).
        """
        return self._pnl

    @property
    def win_rate(self) -> float:
        """
        Returns the win rate.
        """
        try:
            return self._wins/self._n_matched
        except ZeroDivisionError:
            return None

    def _pinger(self, ws: WebSocketApp) -> None:
        """
        A pinger to keep the Bybit WebSocket connection alive.

        Args:
            ws (WebSocketApp): a Bybit WebSocket connection.

        Returns:
            None
        """
        while self._flag:
            ws.send(dumps({"op": "ping"}))
            sleep(20)

    def _on_exec_open(
        self,
        ws: WebSocketApp
    ) -> None:
        """
        on_open handler for the Bybit fast execution WebSocket.

        Args:
            ws (WebSocketApp): A Bybit WebSocket connection.

        Returns:
            None
        """
        # Initializing
        print(f"SessionAcc | Opening the Bybit {self._topic} connection.")

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
                    "args": [self._topic]
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
            None
        """
        msg: Dict[str, Any] = loads(msg)
        try:
            if (
                msg["topic"] == self._topic and
                any(
                    e["symbol"] == self._symbol and
                    e["category"] == self._category for
                    e in msg["data"]
                )
            ):
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
                    (
                        self._buys.append if 
                        e["side"] == "Buy" else 
                        self._sells.append
                    )(
                        {
                            "price": float(e["execPrice"]),
                            "qty": float(e["execQty"]),
                            "isMaker": e["isMaker"],
                        }
                    )

                # Updating pnl and drawdown
                while self._buys and self._sells:
                    # Updating pnl
                    self._n_matched += 1
                    b: Dict[str, Any] = self._buys[0] # Buy
                    s: Dict[str, Any] = self._sells[0] # Sell
                    Q: float = min(b["qty"], s["qty"])
                    vb: float = Q*b["price"]
                    vs: float = Q*s["price"]
                    cb: float = (
                        vb*self._maker 
                        if b["isMaker"] 
                        else vb*self._taker
                    )
                    cs: float = (
                        vs*self._maker 
                        if s["isMaker"] 
                        else vs*self._taker
                    )
                    net_profit: float = vs - vb - cb - cs
                    self._pnl += net_profit
                    if net_profit >= 0:
                        self._wins += 1
                    self._buys[0]["qty"] -= Q
                    self._sells[0]["qty"] -= Q
                    if self._buys[0]["qty"] == 0:
                        del self._buys[0]
                    if self._sells[0]["qty"] == 0:
                        del self._sells[0]

                    # Updating drawdown
                    self._max_pnl = max(self._max_pnl, self._pnl)
                    self._drawdown = max(
                        self._drawdown, 
                        self._max_pnl - self._pnl
                    )
        except KeyError:
            if "success" in msg.keys():
                if not msg["success"]:
                    raise ConnectionError(
                        f"{self._topic} websocket not connected."
                    )

    def connect(self) -> None:
        """
        Connects to ByBit's fast execution stream.

        Return:
            None
        """
        # Defining the on_error handler
        def on_error(
            ws: WebSocketApp, 
            exc: BaseException
        ) -> None:
            raise exc

        # Defining the on_close handler
        def on_close(topic: str) -> Callable:
            def closer(
                ws: WebSocketApp,
                close_status_code: int,
                close_reason: str
            ) -> None:
                print(f"SessionAcc | Bybit {topic} connection closed.")
            return closer

        # Creating the fast execution WebSocket
        self._websockets[self._topic] = WebSocketApp(
            self._mainnet_private,
            on_message=self._on_exec_message,
            on_error=on_error,
            on_open=self._on_exec_open,
            on_close=on_close(topic=self._topic)
        )

        # Running the WebSocket
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

    def kill(self) -> None:
        """
        Kills ALL active WebSockets.

        Returns:
            None
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

    def summary(self) -> None:
        """
        Prints the profit (loss), maximum profit and maximum drawdown to the
        console.

        Example:

            Session Metrics                   Value
            ---------------------------------------
            Session win rate                  0.5100
            Session profit (loss)           100.0000
            Session maximum profit          200.0000
            Session maximum drawdown        100.0000

        Returns:
            None.
        """
        # Format the data into a table
        output: str = f"""
        {"Session Metrics":<30} {"Value":>15}
        {"-"*45}
        {"Session win rate":<30} {round(self.win_rate, 4):>15}
        {"Session profit (loss)":<30} {round(self._pnl, 4):>15}
        {"Session maximum profit":<30} {round(self._max_pnl, 4):>15}
        {"Session maximum drawdown":<30} {round(self._drawdown, 4):>15}
        """

        # Printing
        print(output)
