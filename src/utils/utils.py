# Standard library imports
from os import getenv
from pathlib import Path
from time import sleep

# Third-party imports
from dotenv import load_dotenv

def get_key(key: str) -> str:
    """
    Grabs the environment variable with key == "key".

    Args:
        key (str): A key in the .env file.

    Returns:
        str: The key.
    """
    load_dotenv(dotenv_path = Path.cwd() / ".env")
    s: str = getenv(key)
    try:
        return s
    except Exception:
        raise NameError(f"failed to find the key {repr(key)} in .env")
