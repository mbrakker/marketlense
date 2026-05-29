from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_agentmail_email_tools_module():
	module_root = Path(__file__).resolve().parents[3]
	module_path = module_root / 'examples' / 'integrations' / 'agentmail' / 'email_tools.py'

	agentmail = ModuleType('agentmail')
	agentmail.AsyncAgentMail = object
	agentmail.Message = object
	agentmail.MessageReceivedEvent = object
	agentmail.Subscribe = object
	sys.modules['agentmail'] = agentmail
	sys.modules['agentmail.inboxes'] = ModuleType('agentmail.inboxes')
	sys.modules['agentmail.inboxes.types'] = ModuleType('agentmail.inboxes.types')

	inbox_module = ModuleType('agentmail.inboxes.types.inbox')
	inbox_module.Inbox = object
	sys.modules['agentmail.inboxes.types.inbox'] = inbox_module

	inbox_id_module = ModuleType('agentmail.inboxes.types.inbox_id')
	inbox_id_module.InboxId = str
	sys.modules['agentmail.inboxes.types.inbox_id'] = inbox_id_module

	spec = importlib.util.spec_from_file_location('agentmail_email_tools', module_path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	spec.loader.exec_module(module)
	return module


def test_agentmail_html_to_text_ignores_script_style_bodies() -> None:
	module = _load_agentmail_email_tools_module()

	text = module.EmailTools._html_to_text(
		SimpleNamespace(),
		'<p>Hello</p><script>SECRET DOWNLOAD</script\t\n bar><style>SECRET STYLE</style data-ignored><p>World&nbsp;&amp;</p>',
	)

	assert text == 'Hello World &'
	assert 'SECRET' not in text
