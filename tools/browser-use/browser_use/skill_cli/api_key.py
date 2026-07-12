"""API key management for browser-use CLI."""

import os
import sys


class APIKeyRequired(Exception):
	"""Raised when API key is required but not provided."""

	pass


class APIKeyPersistenceDisabled(Exception):
	"""Raised when an API key is requested to be stored on disk."""

	pass


def require_api_key(feature: str = 'this feature') -> str:
	"""Get API key or raise helpful error.

	Checks in order:
	1. BROWSER_USE_API_KEY environment variable
	2. Interactive prompt (if TTY)
	3. Raises APIKeyRequired with helpful message
	"""
	# 1. Check environment
	key = os.environ.get('BROWSER_USE_API_KEY')
	if key:
		return key

	# 2. Interactive prompt (if TTY)
	if sys.stdin.isatty() and sys.stdout.isatty():
		return prompt_for_api_key(feature)

	# 3. Error with helpful message
	raise APIKeyRequired(
		f"""
╭─────────────────────────────────────────────────────────────╮
│  🔑 Browser-Use API Key Required                            │
│                                                             │
│  {feature} requires an API key.                             │
│                                                             │
│  Get yours at: https://browser-use.com/new-api-key            │
│                                                             │
│  Then set it via:                                           │
│    export BROWSER_USE_API_KEY=your_key_here                 │
│                                                             │
╰─────────────────────────────────────────────────────────────╯
"""
	)


def prompt_for_api_key(feature: str) -> str:
	"""Interactive prompt for API key."""
	print(
		f"""
╭─────────────────────────────────────────────────────────────╮
│  🔑 Browser-Use API Key Required                            │
│                                                             │
│  {feature} requires an API key.                             │
│  Get yours at: https://browser-use.com/new-api-key            │
╰─────────────────────────────────────────────────────────────╯
"""
	)

	try:
		key = input('Enter API key: ').strip()
	except (EOFError, KeyboardInterrupt):
		raise APIKeyRequired('No API key provided')

	if not key:
		raise APIKeyRequired('No API key provided')

	return key


def save_api_key(key: str) -> None:
	"""Reject on-disk API key persistence to prevent clear-text secret storage."""
	if not key:
		raise APIKeyRequired('No API key provided')
	raise APIKeyPersistenceDisabled(
		'Persistent API key storage is disabled. Set BROWSER_USE_API_KEY instead.'
	)


def get_api_key() -> str | None:
	"""Get API key if available, without raising error."""
	try:
		return require_api_key('API key check')
	except APIKeyRequired:
		return None


def check_api_key() -> dict[str, bool | str | None]:
	"""Check API key availability without interactive prompts.

	Returns:
		Dict with keys:
		- 'available': bool - whether API key is configured
		- 'source': str | None - where it came from ('env' or None)
		- 'key_prefix': str | None - first 8 chars of key (for display)
	"""
	# Check environment
	key = os.environ.get('BROWSER_USE_API_KEY')
	if key:
		return {
			'available': True,
			'source': 'env',
			'key_prefix': key[:8] if len(key) >= 8 else key,
		}

	# Not available
	return {
		'available': False,
		'source': None,
		'key_prefix': None,
	}
