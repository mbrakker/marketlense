from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def get_market_lense_root() -> Path:
	"""Return the Market Lense repository root for the vendored Browser Use subtree."""
	return Path(__file__).resolve().parents[3]


def get_market_lense_env_file() -> Path:
	"""Return the authoritative env file path for Browser Use inside this repo."""
	return get_market_lense_root() / '.env'


def load_market_lense_dotenv() -> bool:
	"""Load the root Market Lense .env so vendored Browser Use uses one env surface."""
	return load_dotenv(dotenv_path=get_market_lense_env_file(), override=False)
