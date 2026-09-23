"""GPT-6 browser-use requests retain effort and omit incompatible controls."""

import asyncio
from types import SimpleNamespace

from browser_use.llm.openai.chat import ChatOpenAI


def test_gpt6_browser_use_sends_reasoning_without_sampling() -> None:
	calls = []

	class _Completions:
		async def create(self, **kwargs):
			calls.append(kwargs)
			return SimpleNamespace(
				id='chat_gpt6',
				usage=None,
				choices=[SimpleNamespace(message=SimpleNamespace(content='ok'), finish_reason='stop')],
			)

	class _Model(ChatOpenAI):
		def get_client(self):
			return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

	model = _Model(
		model='gpt-6-luna',
		reasoning_effort='low',
		temperature=0.4,
		top_p=0.8,
		frequency_penalty=0.3,
		seed=42,
	)
	result = asyncio.run(model.ainvoke([]))

	assert result.completion == 'ok'
	assert calls[0]['reasoning_effort'] == 'low'
	for key in ('temperature', 'top_p', 'frequency_penalty', 'seed'):
		assert key not in calls[0]
