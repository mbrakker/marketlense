"""
Simple OpenRouter-backed browser-use example.

@dev You need OPENROUTER_API_KEY in the repository root .env.
"""

import asyncio
import os

from browser_use import Agent, ChatOpenRouter
from browser_use.env import load_market_lense_dotenv as load_dotenv

DEFAULT_MODEL = 'stepfun/step-3.5-flash:free'


async def main() -> None:
	load_dotenv()

	api_key = os.getenv('OPENROUTER_API_KEY')
	if not api_key:
		raise RuntimeError('OPENROUTER_API_KEY is not set in the root .env')

	llm = ChatOpenRouter(
		model=DEFAULT_MODEL,
		api_key=api_key,
		http_referer=os.getenv('OPENROUTER_HTTP_REFERER'),
		temperature=0,
	)
	agent = Agent(
		task='Find the number of stars of the browser-use repo',
		llm=llm,
		use_vision=False,
	)
	await agent.run(max_steps=10)


if __name__ == '__main__':
	asyncio.run(main())
