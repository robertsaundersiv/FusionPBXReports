"""
Shared utilities for agent performance classification and normalization.
"""
from __future__ import annotations

from typing import Dict, Optional


def normalize_agent_id(cdr) -> Optional[str]:
    """Get agent ID, preferring cc_agent over cc_agent_uuid.
    
    cc_agent typically contains the actual agent UUID, while cc_agent_uuid
    may contain call/bridge UUIDs in some cases.
    As a final fallback for records missing call-center agent fields,
    use extension_uuid when available.
    """
    # Prefer cc_agent as it's more reliable for agent identification
    agent = getattr(cdr, "cc_agent", None)
    if agent:
        return agent.strip()
    # Fallback to cc_agent_uuid
    agent_uuid = getattr(cdr, "cc_agent_uuid", None)
    if agent_uuid:
        return agent_uuid.strip()
    extension_uuid = getattr(cdr, "extension_uuid", None)
    if extension_uuid:
        return extension_uuid.strip()
    return None


def normalize_agent_name(cdr, agent_name_map: Dict[str, str]) -> str:
    agent_id = normalize_agent_id(cdr)
    if agent_id and agent_id in agent_name_map:
        return agent_name_map[agent_id]
    fallback = getattr(cdr, "cc_agent", None)
    if fallback:
        return fallback
    return agent_id or "Unknown"


def normalize_queue_name(cdr, queue_name_map: Dict[str, str]) -> Optional[str]:
    cc_queue = getattr(cdr, "cc_queue", None)
    if not cc_queue:
        return None
    if "@" in cc_queue:
        extension = cc_queue.split("@", 1)[0]
    else:
        extension = cc_queue
    return queue_name_map.get(extension, cc_queue)


def get_call_key(cdr) -> Optional[str]:
    bridge_uuid = getattr(cdr, "bridge_uuid", None)
    if bridge_uuid:
        return bridge_uuid
    return getattr(cdr, "xml_cdr_uuid", None)


def _has_call_center_context(cdr) -> bool:
    return any(
        getattr(cdr, field, None)
        for field in (
            "cc_queue_joined_epoch",
            "cc_queue",
            "cc_member_uuid",
            "cc_agent_uuid",
            "cc_agent",
            "call_center_queue_uuid",
        )
    )


def is_handled(cdr) -> bool:
    """Return True when a call center interaction was answered by an agent."""
    if not normalize_agent_id(cdr):
        return False
    if not _has_call_center_context(cdr):
        return False
    answered = any(
        (
            getattr(cdr, "cc_queue_answered_epoch", None),
            getattr(cdr, "answer_epoch", None),
            (getattr(cdr, "billsec", 0) or 0) > 0,
            getattr(cdr, "status", "") == "answered",
        )
    )
    return bool(answered)


def is_missed(cdr) -> bool:
    """Return True for agent-identified calls that were not answered by that agent."""
    if not normalize_agent_id(cdr):
        return False
    if is_handled(cdr):
        return False

    if getattr(cdr, "missed_call", False):
        return True

    cancel_reason = (getattr(cdr, "cc_cancel_reason", "") or "").upper()
    if cancel_reason in {"NO_ANSWER", "AGENT_TIMEOUT", "TIMEOUT"}:
        return True

    hangup_cause = (getattr(cdr, "hangup_cause", "") or "").upper()
    if hangup_cause in {"NO_ANSWER", "ORIGINATOR_CANCEL", "USER_BUSY"}:
        return True

    sip_disposition = (getattr(cdr, "sip_hangup_disposition", "") or "").lower()
    if sip_disposition in {"send_refuse", "recv_refuse", "send_cancel", "recv_cancel"}:
        return True

    if _has_call_center_context(cdr) and (getattr(cdr, "billsec", 0) or 0) == 0:
        return True

    return False


def is_excluded(cdr) -> bool:
    """Exclude voicemail and deflect records when requested."""
    last_app = (getattr(cdr, "last_app", "") or "").lower()
    call_disposition = (getattr(cdr, "call_disposition", "") or "").lower()
    agent_type = (getattr(cdr, "cc_agent_type", "") or "").lower()

    if last_app in {"voicemail", "deflect"}:
        return True
    if call_disposition == "voicemail":
        return True
    if agent_type == "voicemail":
        return True
    return False


def get_agent_record_rank(cdr) -> int:
    score = 0
    if (getattr(cdr, "cc_side", "") or "").lower() == "agent":
        score += 3
    leg = (getattr(cdr, "leg", "") or "").lower()
    if leg in {"b", "bleg", "b-leg"}:
        score += 2
    if (getattr(cdr, "billsec", 0) or 0) > 0:
        score += 1
    if getattr(cdr, "cc_queue_answered_epoch", None):
        score += 1
    return score
