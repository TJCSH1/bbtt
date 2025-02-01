from time import time
from typing import Callable, List

_calls: List[float] = []

def throttle(rate: int) -> Callable:
    """
    Throttles global function calls.

    Args:
        rate (int): Maximum number of function calls per second.

    Returns:
        Callable: A throttling decorator.
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> None:
            global _calls
            _calls = [t for t in _calls if time()-t <= 1]
            while len(_calls) >= rate:
                _calls = [t for t in _calls if time()-t <= 1]
            func(*args, **kwargs)
            _calls.append(time())
        return wrapper
    return decorator
