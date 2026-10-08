from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path

from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxSearchRequest,
)
from src.generators.mail_report_acquisition_generator import (
    select_mail_report_link_candidates,
)
from src.contracts.run_budget import RunBudget
from src.services.mailbox_acquisition_service import search_mailbox_messages
from src.utils.logging import new_run_context


class _ImapProtocolFake:
    def __init__(
        self,
        *,
        uids=(91, 92),
        uid_validity: str = "700",
        html_body: str = "",
    ) -> None:
        self.commands: list[tuple[object, ...]] = []
        self.uid_validity = uid_validity
        self.uids = uids
        self.html_body = html_body

    def __enter__(self) -> _ImapProtocolFake:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        self.commands.append(("login", user, bool(password)))
        return "OK", [b"authenticated"]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"2"]

    def response(self, code: str) -> tuple[str, list[bytes]]:
        self.commands.append(("response", code))
        return "UIDVALIDITY", [self.uid_validity.encode("ascii")]

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        self.commands.append(("uid", command, *args))
        if command == "search":
            return "OK", [" ".join(str(uid) for uid in self.uids).encode("ascii")]
        if command == "fetch":
            raw_uid = args[0]
            uid = (
                raw_uid.decode("ascii") if isinstance(raw_uid, bytes) else str(raw_uid)
            )
            internal_date = (
                "01-Jan-2020 01:00:00 +0000"
                if uid == "91"
                else "02-Jan-2020 02:00:00 +0000"
            )
            message = EmailMessage()
            message["From"] = "Reports <reports@example.test>"
            message["To"] = "reader@example.test"
            message["Subject"] = f"Delivery {uid}"
            message["Date"] = "Fri, 09 Oct 2036 12:00:00 +0000"
            message.set_content("Your requested report is ready.")
            if self.html_body:
                message.add_alternative(self.html_body, subtype="html")
            return "OK", [
                (
                    f'{uid} (UID {uid} INTERNALDATE "{internal_date}" BODY[] '
                    f"{{{len(message.as_bytes())}}})".encode("ascii"),
                    message.as_bytes(),
                )
            ]
        raise AssertionError(f"unexpected UID command: {command}")


def _settings(
    tmp_path: Path, *, user: str = "reader@example.test", mailbox: str = "INBOX"
):
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=0.0,
        poll_interval_seconds=1.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="mail.example.test",
        imap_port=993,
        imap_user=user,
        imap_password="synthetic-test-password",
        imap_mailbox=mailbox,
    )


def _request(
    tmp_path: Path,
    *,
    user: str = "reader@example.test",
    mailbox: str = "INBOX",
    seen=(),
):
    ctx = new_run_context(task_id="imap-protocol-test")
    return (
        MailboxSearchRequest(
            schema_version="1.0",
            settings=_settings(tmp_path, user=user, mailbox=mailbox),
            delivery_email="reader@example.test",
            source_url="https://publisher.example.test/report-form",
            report_title="Annual report",
            publisher_name="Example Publisher",
            query_terms=["Annual", "report"],
            seen_provider_message_ids=list(seen),
            run_budget=RunBudget(
                schema_version="1.0",
                run_id=ctx.run_id,
                publisher_name="Example Publisher",
                usage_db_path=str(tmp_path / f"usage-{ctx.run_id}.sqlite"),
            ),
        ),
        ctx,
    )


def _search(request, ctx, client: _ImapProtocolFake):
    return search_mailbox_messages(
        request,
        ctx,
        imap_connection_factory=lambda host, port: client,
    )


def test_imap_search_is_read_only_uid_based_and_uses_internaldate(tmp_path) -> None:
    request, ctx = _request(tmp_path)
    client = _ImapProtocolFake()

    result = _search(request, ctx, client)

    assert [message.received_at_utc for message in result.messages] == [
        "2020-01-02T02:00:00Z",
        "2020-01-01T01:00:00Z",
    ]
    assert result.messages[0].provider_message_id.startswith("imap:")
    assert result.messages[0].provider_message_id.endswith(":700:92")
    assert ("select", "INBOX", True) in client.commands
    searches = [
        command for command in client.commands if command[:2] == ("uid", "search")
    ]
    assert len(searches) == 1
    assert searches[0][2] == "SINCE"
    fetches = [
        command for command in client.commands if command[:2] == ("uid", "fetch")
    ]
    assert len(fetches) == 2
    assert all("BODY.PEEK[]" in str(command[-1]) for command in fetches)
    assert all("RFC822" not in str(command[-1]) for command in fetches)
    remaining_request, remaining_ctx = _request(tmp_path)
    remaining = _search(
        remaining_request,
        remaining_ctx,
        _ImapProtocolFake(uids=(92,)),
    )
    assert (
        remaining.messages[0].provider_message_id
        == result.messages[0].provider_message_id
    )


def test_imap_identity_scopes_account_and_resets_on_uidvalidity_change(
    tmp_path, caplog
) -> None:
    first_request, first_ctx = _request(tmp_path, user="first@example.test")
    first = _search(first_request, first_ctx, _ImapProtocolFake())
    second_request, second_ctx = _request(tmp_path, user="second@example.test")
    second = _search(second_request, second_ctx, _ImapProtocolFake())
    assert (
        first.messages[0].provider_message_id != second.messages[0].provider_message_id
    )
    mailbox_request, mailbox_ctx = _request(
        tmp_path, user="first@example.test", mailbox="Archive"
    )
    other_mailbox = _search(mailbox_request, mailbox_ctx, _ImapProtocolFake())
    assert (
        first.messages[0].provider_message_id
        != other_mailbox.messages[0].provider_message_id
    )

    rollover_request, rollover_ctx = _request(
        tmp_path,
        user="first@example.test",
        seen=[first.messages[0].provider_message_id],
    )
    with caplog.at_level(
        logging.INFO, logger="market_lense.mailbox_acquisition_service"
    ):
        rolled_over = _search(
            rollover_request,
            rollover_ctx,
            _ImapProtocolFake(uid_validity="701"),
        )

    assert len(rolled_over.messages) == 2
    assert "mailbox_imap_uidvalidity_cursor_reset" in caplog.text


def test_imap_legacy_sequence_ids_do_not_suppress_uid_messages(tmp_path) -> None:
    request, ctx = _request(tmp_path, seen=["91", "92"])

    result = _search(request, ctx, _ImapProtocolFake())

    assert sorted(
        message.provider_message_id.rsplit(":", 1)[-1] for message in result.messages
    ) == ["91", "92"]


def test_imap_html_link_context_selects_opaque_report_cta_without_negative_links(
    tmp_path,
) -> None:
    report_url = (
        "https://cdn.example.test/Report/Annual.pdf?token=a%2Fb+Case"
        "&X-Amz-Signature=AbC%2f+Z."
    )
    unsubscribe_url = "https://cdn.example.test/unsubscribe?token=private"
    escaped_report_url = report_url.replace("&", "&amp;")
    request, ctx = _request(tmp_path)
    client = _ImapProtocolFake(
        uids=(91,),
        html_body=(
            "<div><p>Your Annual Report is ready.</p>"
            f'<a href="{escaped_report_url}">Download the Annual Report</a>'
            "</div><div>"
            f'<a href="{unsubscribe_url}">Unsubscribe</a>'
            "</div>"
        ),
    )

    message = _search(request, ctx, client).messages[0]
    candidates = select_mail_report_link_candidates(
        messages=[message],
        source_url="https://example.test/request-report",
        report_title="Annual Report",
        publisher_name="Example Publisher",
        ctx=ctx,
    )

    assert message.links == [report_url, unsubscribe_url]
    assert message.link_references[0].anchor_text == "Download the Annual Report"
    assert "Annual Report" in message.link_references[0].nearby_text
    assert [candidate.url for candidate in candidates] == [report_url]
