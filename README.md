# Bybit Trading Tools

This Python package offers a streamlined interface for managing orders, 
positions, and real-time data via Bybit’s WebSocket API. It simplifies 
interaction with Bybit’s private API, enabling efficient order management, 
position tracking, and market activity updates. Additionally, it equips users 
with tools to monitor session performance metrics, including accumulated profit 
and loss and maximum drawdown.

## Features

- **Order Management**: Place, amend, and cancel orders.
- **Real-time Data**: Subscribe to real-time updates on orders, positions, and 
    trades, profit and loss, and maximum drawdown.
- **Rate Limiting**: Handles API rate limits gracefully.
- **Threading**: Uses separate threads for WebSocket connections to handle 
    multiple streams simultaneously.

## Example Usage of the Order Management System (OMS)

### Initialize the OMS

Create an instance of the `Oms` class by specifying your trading pair `symbol`
and `category` (e.g., `spot`, `linear`, `inverse` or `option`). Optionally, 
specify the rate limit for API calls (per second).

```python
from bbtt import Oms

# Initialize the OMS for BTC/USDT trading
oms: Oms = Oms(
    symbol="BTCUSDT",
    category="linear",
    api_rate=10
)

# Connecting the OMS
oms.connect()
```

### Placing an Order

You can create a new order by calling the `create_order` method. For example,
to place a limit buy order:

```python
oms.create_order(
    price="98000",
    qty="0.2",
    side="Buy",
    orderType="Limit",
    timeInForce="PostOnly",
    isLeverage=1,
    orderLinkId="UUID1234"
)
```

### Viewing Position

Use: 

```python
oms.position
```

to check your current trading position (i.e., units held). The returned value 
is a `float`, where positive values represent long positions and nevative 
values represent short positions.

### Canceling an Order

To cancel an active limit order, simply use the `cancel_order` method:

```python
oms.cancel_order(order_link_id="UUID1234")
```

### Get Order Status

You can check the current status of an order using its `orderLinkId`:

```python
status: str = oms.order_status(order_link_id="UUID1234")
print(f"Order Status: {status}")
```

### Disconnecting
When you're done, you can terminate the WebSocket connections:

```python
oms.kill()
```

## Example Usage of the Session Accounting Class

### Initialize the Session Accounting

Create an instance of the `SessionAcc` class by specifying your trading pair 
`symbol`, `category` (e.g., `spot`, `linear`, `inverse` or `option`), and fee
rates, `maker`, `taker`.

```python
from bbtt import SessionAcc

# Initialize the session accounting for BTC/USDT trading
session_acc: SessionAcc = SessionAcc(
    symbol="BTCUSDT",
    category="linear",
    maker=0.02/100,
    taker=0.055/100
)

# Connect
session_acc.connect()
```

### View the Attributes

You can view the 

 - maximum drawdown 
 - maximum profit (loss)
 - current profit (loss)

during the trading session through the `drawdown`, `max_pnl`, and `pnl` 
attributes:

```python
# Accessing the attributes
drawdown: float = session_acc.drawdown
max_pnl: float = session_acc.max_pnl
pnl: float = session_acc.pnl

# Printing
print(f"The maximum drawdown during the trading session was {drawdown}")
print(f"The maximum profit (loss) during the trading session was {max_pnl}")
print(f"The current profit (loss) is {max_pnl}")
```

### Session Performance Summary

Alternatively, you may access the attributes above in a nice table by calling
the `summary()` method:

```python
# Printing the session summary
session_acc.summary()
```

```bash
Session Metrics                   Value
---------------------------------------------
Session profit (loss)           100.0000 USDT
Session maximum profit          200.0000 USDT
Session maximum drawdown        100.0000 USDT
```

### Disconnecting

When you're done, you can terminate the WebSocket connections via the `kill()`
method:

```python
session_acc.kill() # Closing the websocket conections
```

## API Key and Secret Configuration

To interact with Bybit's API, you'll need to provide your API key and secret.
**For security reasons, you must not hard-code these values in your scripts.
Instead, store them in a `.env` file.**

### Why Use a `.env` File?

Storing sensitive information like API keys and secrets in a `.env` file
ensures that:
- Your credentials are not exposed in your codebase.
- They remain secure and can be easily ignored in version control systems using
`.gitignore`.

### Setting Up the `.env` File

1. Create a `.env` file in the root directory of your project.
2. Add your API key and secret in the following format:
```bash
api_key=your_api_key_here
api_secret=your_api_secret_here
```
3. Ensure your `.env` file is added to your `.gitignore` file to prevent
   accidental exposure:
```bash
# Add this to your .gitignore
.env
```

The `Oms` and `SessionAcc` classes automatically read your API key and secret 
from the `.env` file. There's no need for additional configuration.

## Initializing Oms

### `symbol: str`
- The trading pair symbol (e.g., `"BTCUSDT"`).

### `category: str`
- Instrument category (`"spot"`, `"linear"`, `"inverse"`, `"option"`).

### `api_rate: Optional[int]`
- The rate limit for API calls per second. Defaults to 10.

### `mainnet_private: Optional[str]`
- URL for Bybit's private API WebSocket. Defaults to
  wss://stream.bybit.com/v5/private.

### `mainnet_trade: Optional[str]`
- URL for Bybit's trade API WebSocket. Defaults to
  wss://stream.bybit.com/v5/trade.

## Oms Attributes

The class provides access to the following attributes:

### `active (bool)`
- **Description:** Indicates whether there are any active orders.

### `active_orders (Dict[str, Dict[str, Any]])`
- **Description:** A dictionary containing active orders, keyed by order link 
  ID.

### `position (float)`
- **Description:** The signed position size (units held) for the tracked 
  symbol, where positive values represent long positions and negative values
  represent short positions.

## Oms Methods

### `connect() -> None`
- **Description:** Establishes WebSocket connections for orders, positions and 
  trades.

### `create_order(**kwargs) -> None`
- **Description:** Creates a new market or limit order.
- **Arguments:** 
  - `kwargs`: Order parameters (EXCLUDING category and symbol). See Bybit API 
    documentation for available options: 
    https://bybit-exchange.github.io/docs/v5/order/create-order.
- **Remark:** Note that a order link ID will be automatically generated if not 
  passed as an argument to the method. The order link IDs of active orders can
  be access via:
  ```python
  order_link_ids: List[str] = list(oms.active_orders.keys())
  ```

### `amend_order(**kwargs) -> None`
- **Description:** Amends an active limit order.
- **Arguments:** 
  - `kwargs`: Order parameters (EXCLUDING category and symbol). See Bybit API 
    documentation for available options: 
    https://bybit-exchange.github.io/docs/v5/order/amend-order.

### `cancel_order(order_link_id: str) -> None`
- **Description:** Cancels an active limit order using its unique order link 
  ID.
- **Arguments:** 
  - `order_link_id (str)`: The unique identifier of the order.

### `order_status(order_link_id: str) -> str`
- **Description:** Retrieves the status of an order based on its unique order 
  link ID.
- **Arguments:** 
  - `order_link_id (str)`: The unique identifier of the order.
- **Returns:**
  - the current status of the order, which can be one of the following:
    ```python
    [
        "",
        "Unsubmitted",
        "New",
        "Cancelled",
        "PartiallyFilled",
        "Filled"
    ]
    ```
    - `""` indicates that the order hasn't been received by Bybit.
    - `"Unsubmitted"` indicates that the order was not sent to Bybit. 
    - `"New"` indicates that the order is posted and active.
    - `"Cancelled"` indicates that the order has been cancelled. 
    - `"PartiallyFilled"` indicates that the order is partially filled.
    - `"Filled"` indicates that the order has been executed in full.

### `remove_status(order_link_id: str) -> None`
- **Description:** Removes the entry associated with the given order link ID. 
- **Arguments:** 
  - `order_link_id (str)`: The unique identifier of the order.

### `reconnect() -> None`
- **Description:** Reconnects the WebSockets.

### `kill() -> None`
- **Description:** Kills ALL active WebSockets.

## Initializing SessionAcc

### `symbol: str`
- The trading pair symbol (e.g., `"BTCUSDT"`).

### `category: str`
- Instrument category (`"spot"`, `"linear"`, `"inverse"`, `"option"`).

### `maker: float`
- The maker fee rate, e.g. `0.02/100`.

### `taker: float`
- The taker fee rate, e.g. `0.055/100`.

## SessionAcc Methods

### `connect() -> None`
- **Description:** Establishes WebSocket connections for session accounting.

### `summary() -> None`
- **Description:** Prints the maximum drawdown, maximum profit (loss) and 
  current profit (loss) as a table.

### `kill() -> None`
- **Description:** Kills ALL active WebSockets.

## License

This project is licensed under the MIT license - see the [LICENSE](LICENSE) 
file for details.

## Contact

For any issues or questions, please open an issue on the repository, or contact
tj3119915@gmail.com.
