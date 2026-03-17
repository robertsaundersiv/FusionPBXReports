"""
Unit tests for agent missed-call classification behavior.
"""

from app.utils.agent_performance_utils import is_missed


class MockCDR:
    def __init__(self, **kwargs):
        self.cc_agent = kwargs.get("cc_agent", "agent-1")
        self.cc_agent_uuid = kwargs.get("cc_agent_uuid")
        self.extension_uuid = kwargs.get("extension_uuid")
        self.cc_queue = kwargs.get("cc_queue", "38328@default")
        self.cc_queue_joined_epoch = kwargs.get("cc_queue_joined_epoch", 1773778413)
        self.cc_member_uuid = kwargs.get("cc_member_uuid", "member-1")
        self.call_center_queue_uuid = kwargs.get("call_center_queue_uuid", "queue-1")
        self.cc_queue_answered_epoch = kwargs.get("cc_queue_answered_epoch")
        self.answer_epoch = kwargs.get("answer_epoch")
        self.billsec = kwargs.get("billsec", 0)
        self.status = kwargs.get("status", "")
        self.missed_call = kwargs.get("missed_call", False)
        self.cc_cancel_reason = kwargs.get("cc_cancel_reason")
        self.hangup_cause = kwargs.get("hangup_cause")
        self.sip_hangup_disposition = kwargs.get("sip_hangup_disposition")


def test_user_busy_does_not_count_as_missed_even_with_missed_flag():
    record = MockCDR(
        missed_call=True,
        hangup_cause="USER_BUSY",
    )

    assert is_missed(record) is False


def test_sip_refuse_does_not_count_as_missed():
    record = MockCDR(
        missed_call=True,
        sip_hangup_disposition="recv_refuse",
    )

    assert is_missed(record) is False


def test_timeout_still_counts_as_missed_when_not_busy():
    record = MockCDR(
        cc_cancel_reason="AGENT_TIMEOUT",
        hangup_cause="NO_ANSWER",
        missed_call=False,
    )

    assert is_missed(record) is True
