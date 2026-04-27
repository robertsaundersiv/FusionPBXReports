"""Tests for queue-entry answered detection fallback behavior."""

from types import SimpleNamespace

from app.api.dashboard import is_queue_entry_answered, is_queue_entry_voicemail


def test_queue_entry_answered_by_cc_queue_answered_epoch() -> None:
    records = [SimpleNamespace(cc_queue_answered_epoch=1773779000, answer_epoch=None, billsec=0)]
    assert is_queue_entry_answered(records) is True


def test_queue_entry_answered_by_answer_epoch_fallback() -> None:
    records = [SimpleNamespace(cc_queue_answered_epoch=None, answer_epoch=1773779000, billsec=0, hangup_cause="NORMAL_CLEARING")]
    assert is_queue_entry_answered(records) is True


def test_queue_entry_not_answered_by_billsec_only() -> None:
    records = [SimpleNamespace(cc_queue_answered_epoch=None, answer_epoch=None, billsec=45, hangup_cause="NORMAL_CLEARING")]
    assert is_queue_entry_answered(records) is False


def test_queue_entry_not_answered_by_answer_epoch_with_non_clear_hangup() -> None:
    records = [SimpleNamespace(cc_queue_answered_epoch=None, answer_epoch=1773779000, billsec=0, hangup_cause="NO_ANSWER")]
    assert is_queue_entry_answered(records) is False


def test_queue_entry_not_answered_when_no_signals() -> None:
    records = [SimpleNamespace(cc_queue_answered_epoch=None, answer_epoch=None, billsec=0)]
    assert is_queue_entry_answered(records) is False


def test_queue_entry_voicemail_route_not_answered_by_fallback() -> None:
    records = [
        SimpleNamespace(
            cc_queue_answered_epoch=None,
            answer_epoch=1773779000,
            billsec=0,
            hangup_cause="NORMAL_CLEARING",
            destination_number="*99323362",
            caller_destination=None,
            last_app=None,
            last_arg=None,
            call_disposition=None,
            cc_agent_type=None,
            voicemail_message=None,
        )
    ]
    assert is_queue_entry_answered(records) is False


def test_queue_entry_voicemail_route_classified_as_voicemail() -> None:
    records = [
        SimpleNamespace(
            cc_queue_answered_epoch=None,
            answer_epoch=1773779000,
            billsec=0,
            hangup_cause="NORMAL_CLEARING",
            destination_number="*9972012",
            caller_destination=None,
            last_app=None,
            last_arg=None,
            call_disposition=None,
            cc_agent_type=None,
            voicemail_message=None,
        )
    ]
    assert is_queue_entry_voicemail(records) is True
