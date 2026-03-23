"""Tests for outbound handled-call classification fallbacks."""

from app.utils.agent_performance_utils import is_handled


class MockCDR:
    def __init__(self, **kwargs):
        self.cc_agent = kwargs.get("cc_agent")
        self.cc_agent_uuid = kwargs.get("cc_agent_uuid")
        self.extension_uuid = kwargs.get("extension_uuid")
        self.cc_queue = kwargs.get("cc_queue")
        self.cc_queue_joined_epoch = kwargs.get("cc_queue_joined_epoch")
        self.cc_member_uuid = kwargs.get("cc_member_uuid")
        self.call_center_queue_uuid = kwargs.get("call_center_queue_uuid")
        self.cc_queue_answered_epoch = kwargs.get("cc_queue_answered_epoch")
        self.answer_epoch = kwargs.get("answer_epoch")
        self.billsec = kwargs.get("billsec", 0)
        self.status = kwargs.get("status", "")
        self.direction = kwargs.get("direction")


def test_outbound_without_call_center_context_counts_as_handled_when_answered():
    record = MockCDR(
        direction="outbound",
        extension_uuid="ext-uuid-1",
        answer_epoch=1710000000,
        billsec=45,
    )

    assert is_handled(record) is True


def test_outbound_without_call_center_context_not_handled_when_unanswered():
    record = MockCDR(
        direction="outbound",
        extension_uuid="ext-uuid-1",
        answer_epoch=None,
        billsec=0,
        status="",
    )

    assert is_handled(record) is False


def test_inbound_without_call_center_context_is_not_handled():
    record = MockCDR(
        direction="inbound",
        extension_uuid="ext-uuid-1",
        answer_epoch=1710000000,
        billsec=30,
    )

    assert is_handled(record) is False
