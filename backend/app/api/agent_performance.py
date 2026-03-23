"""
Agent performance API routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict
import re

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import or_, desc
from sqlalchemy.orm import Session, load_only

from app.auth import get_current_user, ROLE_SUPER_ADMIN
from app.database import get_db
from app.models import CDRRecord, Queue, Agent, Extension
from app.utils.agent_performance_utils import (
    normalize_agent_id,
    normalize_agent_name,
    normalize_queue_name,
    get_call_key,
    get_agent_interaction_key,
    is_handled,
    is_missed,
    is_excluded,
    get_agent_record_rank,
)

router = APIRouter(prefix="/api/v1/agent-performance", tags=["agent-performance"])


AGENT_ANALYTICS_COLUMNS = (
    CDRRecord.xml_cdr_uuid,
    CDRRecord.start_epoch,
    CDRRecord.answer_epoch,
    CDRRecord.end_epoch,
    CDRRecord.direction,
    CDRRecord.cc_queue,
    CDRRecord.cc_queue_joined_epoch,
    CDRRecord.cc_queue_answered_epoch,
    CDRRecord.cc_queue_terminated_epoch,
    CDRRecord.cc_queue_canceled_epoch,
    CDRRecord.cc_agent_uuid,
    CDRRecord.cc_agent,
    CDRRecord.cc_agent_type,
    CDRRecord.cc_agent_bridged,
    CDRRecord.cc_side,
    CDRRecord.cc_member_uuid,
    CDRRecord.extension_uuid,
    CDRRecord.call_center_queue_uuid,
    CDRRecord.bridge_uuid,
    CDRRecord.leg,
    CDRRecord.status,
    CDRRecord.missed_call,
    CDRRecord.cc_cancel_reason,
    CDRRecord.cc_cause,
    CDRRecord.hangup_cause,
    CDRRecord.sip_hangup_disposition,
    CDRRecord.last_app,
    CDRRecord.call_disposition,
    CDRRecord.caller_id_name,
    CDRRecord.caller_id_number,
    CDRRecord.destination_number,
    CDRRecord.duration,
    CDRRecord.billsec,
    CDRRecord.hold_accum_seconds,
    CDRRecord.rtp_audio_in_mos,
)


def optimize_cdr_query(query):
    return query.options(load_only(*AGENT_ANALYTICS_COLUMNS))


def parse_csv_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def get_time_window(
    start: Optional[datetime],
    end: Optional[datetime],
) -> tuple[int, int]:
    if not end:
        end = datetime.now(timezone.utc)
    if not start:
        start = end - timedelta(days=7)
    start_epoch = int(start.timestamp())
    end_epoch = int(end.replace(hour=23, minute=59, second=59).timestamp())
    return start_epoch, end_epoch


def build_queue_extension_map(db: Session, queue_ids: List[str]) -> Dict[str, str]:
    if not queue_ids:
        queues = db.query(Queue).filter(Queue.enabled == True).all()
    else:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
    return {q.queue_extension: q.name for q in queues if q.queue_extension}


def build_queue_lookup(db: Session, queue_ids: List[str]) -> Dict[str, Queue]:
    if not queue_ids:
        queues = db.query(Queue).filter(Queue.enabled == True).all()
    else:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
    return {q.queue_extension: q for q in queues if q.queue_extension}


def build_agent_name_map(db: Session, enabled_only: bool = True) -> Dict[str, str]:
    query = db.query(Agent)
    if enabled_only:
        query = query.filter(Agent.enabled == True)
    agents = query.all()
    name_map = {agent.agent_uuid: agent.agent_name for agent in agents if agent.agent_uuid and agent.agent_name}

    # Fallback mapping for records where extension_uuid is present but
    # call-center agent identifiers are not populated.
    extensions = db.query(Extension).all()
    for extension in extensions:
        if extension.extension_uuid and extension.user_name:
            name_map[extension.extension_uuid] = extension.user_name

    return name_map


def build_agent_resolution_context(db: Session, enabled_only: bool = True) -> Dict[str, object]:
    query = db.query(Agent)
    if enabled_only:
        query = query.filter(Agent.enabled == True)
    agents = query.all()
    extensions = db.query(Extension).all()

    agent_name_map: Dict[str, str] = {}
    alias_to_agent_id: Dict[str, str] = {}
    caller_number_to_agent_id: Dict[str, str] = {}
    known_name_to_agent_id: Dict[str, str] = {}
    name_word_map: List[tuple[Set[str], str]] = []

    for agent in agents:
        if not agent.agent_name:
            continue

        canonical_agent_id = (
            str(agent.agent_uuid).strip()
            if agent.agent_uuid
            else (str(agent.extension).strip() if agent.extension else str(agent.agent_name).strip())
        )
        if not canonical_agent_id:
            continue

        agent_name_map[canonical_agent_id] = agent.agent_name

        aliases = []
        if agent.agent_uuid:
            aliases.append(str(agent.agent_uuid).strip())
        if agent.extension:
            aliases.append(str(agent.extension).strip())
            caller_number_to_agent_id[str(agent.extension).strip()] = canonical_agent_id
        if agent.agent_contact:
            aliases.append(str(agent.agent_contact).strip())
            contact_match = re.search(r"user/(\d{3,6})@", str(agent.agent_contact))
            if contact_match:
                caller_number_to_agent_id[contact_match.group(1)] = canonical_agent_id

        normalized_name = str(agent.agent_name).strip().lower()
        if normalized_name:
            known_name_to_agent_id[normalized_name] = canonical_agent_id
            words = set(re.split(r"[\s\-_]+", normalized_name))
            words.discard("")
            if len(words) >= 2:
                name_word_map.append((words, canonical_agent_id))

        aliases.append(str(agent.agent_name).strip())
        for alias in aliases:
            if alias:
                alias_to_agent_id[alias] = canonical_agent_id

    for extension in extensions:
        extension_uuid = str(extension.extension_uuid).strip() if extension.extension_uuid else None
        extension_number = str(extension.extension).strip() if extension.extension else None
        user_name = str(extension.user_name).strip() if extension.user_name else None

        mapped_agent_id: Optional[str] = None
        if extension_number and extension_number in caller_number_to_agent_id:
            mapped_agent_id = caller_number_to_agent_id[extension_number]
        elif user_name and user_name.lower() in known_name_to_agent_id:
            mapped_agent_id = known_name_to_agent_id[user_name.lower()]

        if extension_uuid and mapped_agent_id:
            alias_to_agent_id[extension_uuid] = mapped_agent_id
            if user_name:
                agent_name_map.setdefault(mapped_agent_id, user_name)
        elif extension_uuid and user_name:
            # Preserve legacy fallback where extension UUID acts as agent identity.
            alias_to_agent_id.setdefault(extension_uuid, extension_uuid)
            agent_name_map.setdefault(extension_uuid, user_name)
            if extension_number and extension_number not in caller_number_to_agent_id:
                caller_number_to_agent_id[extension_number] = extension_uuid

    return {
        "agent_name_map": agent_name_map,
        "alias_to_agent_id": alias_to_agent_id,
        "caller_number_to_agent_id": caller_number_to_agent_id,
        "known_name_to_agent_id": known_name_to_agent_id,
        "name_word_map": name_word_map,
    }


def resolve_agent_id(record: CDRRecord, resolution_ctx: Dict[str, object]) -> Optional[str]:
    agent_id, _ = resolve_agent_identity(record, resolution_ctx)
    return agent_id


def should_count_missed_call(record: CDRRecord, include_outbound: bool, attribution_source: Optional[str]) -> bool:
    if not is_missed(record):
        return False

    # Miss/No-answer should only be based on inbound/local queue interactions.
    direction = (getattr(record, "direction", "") or "").lower()
    if direction not in {"inbound", "local"}:
        return False

    # When include_outbound is enabled, agent matching can broaden via caller-based attribution.
    # Keep missed counts stable by excluding caller-attributed misses from this mode.
    if include_outbound and attribution_source in {
        "caller_number",
        "caller_name_exact",
        "caller_name_extension",
        "caller_name_fuzzy",
    }:
        return False

    return True


def has_explicit_agent_alias_match(record: CDRRecord, expanded_agent_ids: Set[str]) -> bool:
    if not expanded_agent_ids:
        return True

    for field_name in ("cc_agent", "cc_agent_uuid", "extension_uuid"):
        raw_value = getattr(record, field_name, None)
        if raw_value and str(raw_value).strip() in expanded_agent_ids:
            return True

    normalized = normalize_agent_id(record)
    return bool(normalized and normalized in expanded_agent_ids)


def resolve_agent_identity(record: CDRRecord, resolution_ctx: Dict[str, object]) -> tuple[Optional[str], Optional[str]]:
    alias_to_agent_id: Dict[str, str] = resolution_ctx["alias_to_agent_id"]  # type: ignore[assignment]
    caller_number_to_agent_id: Dict[str, str] = resolution_ctx["caller_number_to_agent_id"]  # type: ignore[assignment]
    known_name_to_agent_id: Dict[str, str] = resolution_ctx["known_name_to_agent_id"]  # type: ignore[assignment]
    name_word_map: List[tuple[Set[str], str]] = resolution_ctx["name_word_map"]  # type: ignore[assignment]

    for field_name, source in (
        ("cc_agent", "cc_agent"),
        ("cc_agent_uuid", "cc_agent_uuid"),
        ("extension_uuid", "extension_uuid"),
    ):
        raw_value = getattr(record, field_name, None)
        if raw_value:
            candidate = str(raw_value).strip()
            if candidate in alias_to_agent_id:
                return alias_to_agent_id[candidate], source

    caller_number = (getattr(record, "caller_id_number", "") or "").strip()
    if caller_number and caller_number in caller_number_to_agent_id:
        return caller_number_to_agent_id[caller_number], "caller_number"

    caller_label = (getattr(record, "caller_id_name", "") or "").strip()
    if caller_label:
        label_key = caller_label.lower()
        if label_key in known_name_to_agent_id:
            return known_name_to_agent_id[label_key], "caller_name_exact"

        for token in re.findall(r"\b\d{3,6}\b", caller_label):
            mapped = caller_number_to_agent_id.get(token)
            if mapped:
                return mapped, "caller_name_extension"

        caller_words = set(re.split(r"[\s\-_]+", label_key))
        caller_words.discard("")
        if len(caller_words) >= 2:
            for known_words, known_agent_id in name_word_map:
                if caller_words.issubset(known_words) or known_words.issubset(caller_words):
                    return known_agent_id, "caller_name_fuzzy"

    fallback_agent_id = normalize_agent_id(record)
    if fallback_agent_id:
        return alias_to_agent_id.get(fallback_agent_id, fallback_agent_id), "raw_fallback"

    return None, None


def expand_agent_filters(agent_ids: List[str], resolution_ctx: Dict[str, object]) -> tuple[List[str], List[str]]:
    if not agent_ids:
        return [], []

    alias_to_agent_id: Dict[str, str] = resolution_ctx["alias_to_agent_id"]  # type: ignore[assignment]
    caller_number_to_agent_id: Dict[str, str] = resolution_ctx["caller_number_to_agent_id"]  # type: ignore[assignment]

    canonical_ids: Set[str] = set()
    raw_agent_ids: Set[str] = set()
    for agent_id in agent_ids:
        if not agent_id:
            continue
        canonical_ids.add(alias_to_agent_id.get(agent_id, agent_id))
        raw_agent_ids.add(agent_id)

    expanded_agent_ids: Set[str] = set(raw_agent_ids)
    for alias, canonical in alias_to_agent_id.items():
        if canonical in canonical_ids:
            expanded_agent_ids.add(alias)

    caller_number_filters = [
        number
        for number, canonical in caller_number_to_agent_id.items()
        if canonical in canonical_ids
    ]

    return list(expanded_agent_ids), caller_number_filters


def canonicalize_requested_agent_id(agent_id: str, resolution_ctx: Dict[str, object]) -> str:
    alias_to_agent_id: Dict[str, str] = resolution_ctx["alias_to_agent_id"]  # type: ignore[assignment]
    return alias_to_agent_id.get(agent_id, agent_id)


def get_accessible_agent_identifiers(db: Session, current_user: dict) -> Optional[Set[str]]:
    """Return allowed agent identifiers for the current user.

    Visibility restrictions were removed, so all authenticated users share the same scope.
    """
    return None


def apply_common_filters(
    query,
    start_epoch: int,
    end_epoch: int,
    queue_extensions: List[str],
    agent_ids: List[str],
    caller_number_filters: List[str],
    include_outbound: bool,
    accessible_agent_ids: Optional[Set[str]] = None,
    all_known_caller_numbers: Optional[List[str]] = None,
):
    query = query.filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
    )

    if not include_outbound:
        query = query.filter(CDRRecord.direction == "inbound")

    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        queue_filter = or_(*extension_filters)
        if include_outbound:
            # Outbound calls generally don't have cc_queue; keep them when
            # include_outbound is enabled even if queue filters are selected.
            query = query.filter(or_(queue_filter, CDRRecord.direction == "outbound"))
        else:
            query = query.filter(queue_filter)

    if agent_ids:
        agent_filters = [
            CDRRecord.cc_agent_uuid.in_(agent_ids),
            CDRRecord.cc_agent.in_(agent_ids),
            CDRRecord.extension_uuid.in_(agent_ids),
        ]
        if caller_number_filters:
            agent_filters.append(CDRRecord.caller_id_number.in_(caller_number_filters))
        query = query.filter(or_(*agent_filters))

    if accessible_agent_ids is not None:
        if not accessible_agent_ids:
            query = query.filter(CDRRecord.id == -1)
        else:
            query = query.filter(
                or_(
                    CDRRecord.cc_agent_uuid.in_(list(accessible_agent_ids)),
                    CDRRecord.cc_agent.in_(list(accessible_agent_ids)),
                )
            )

    # For outbound calls, also allow records matched only by caller_id_number
    # (pure outbound CDRs lack cc_agent_uuid / cc_agent / extension_uuid).
    cc_context_filter = or_(
        CDRRecord.cc_agent_uuid.isnot(None),
        CDRRecord.cc_agent.isnot(None),
        CDRRecord.extension_uuid.isnot(None),
    )
    if include_outbound and all_known_caller_numbers:
        query = query.filter(
            or_(
                cc_context_filter,
                CDRRecord.caller_id_number.in_(all_known_caller_numbers),
            )
        )
    else:
        query = query.filter(cc_context_filter)

    return query


def choose_record(existing, candidate):
    if not existing:
        return candidate
    if get_agent_record_rank(candidate) > get_agent_record_rank(existing):
        return candidate
    return existing


def resolve_queue_key(record: CDRRecord, queue_lookup: Dict[str, Queue]) -> Optional[Dict[str, str]]:
    cc_queue = record.cc_queue or ""
    extension = cc_queue.split("@", 1)[0] if "@" in cc_queue else cc_queue
    if not extension:
        return None
    queue = queue_lookup.get(extension)
    if queue:
        return {"queue_id": str(queue.queue_id), "queue_name": queue.name}
    return {"queue_id": extension, "queue_name": extension}


def can_view_agent_missed_calls(current_user: dict) -> bool:
    return (current_user or {}).get("role") == ROLE_SUPER_ADMIN


def can_view_agent_attribution_diagnostics(current_user: dict) -> bool:
    return (current_user or {}).get("role") == ROLE_SUPER_ADMIN


@router.get("/leaderboard")
async def get_agent_leaderboard(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    queues: Optional[str] = Query(None),
    agents: Optional[str] = Query(None),
    include_outbound: bool = Query(False),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_epoch, end_epoch = get_time_window(start, end)
    show_missed_calls = can_view_agent_missed_calls(current_user)
    show_attribution_diagnostics = can_view_agent_attribution_diagnostics(current_user)
    queue_ids = parse_csv_list(queues)
    agent_ids = parse_csv_list(agents)
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys()) if queue_ids else []
    # Include all agents (even disabled) for historical name resolution
    resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
    agent_name_map: Dict[str, str] = resolution_ctx["agent_name_map"]  # type: ignore[assignment]
    expanded_agent_ids, caller_number_filters = expand_agent_filters(agent_ids, resolution_ctx)
    expanded_agent_id_set = set(expanded_agent_ids)
    alias_to_agent_id: Dict[str, str] = resolution_ctx["alias_to_agent_id"]  # type: ignore[assignment]
    requested_canonical_agent_ids: Set[str] = {
        alias_to_agent_id.get(agent_id, agent_id)
        for agent_id in agent_ids
        if agent_id
    }

    if queue_ids and not queue_extensions:
        return {
            "start": datetime.fromtimestamp(start_epoch).isoformat(),
            "end": datetime.fromtimestamp(end_epoch).isoformat(),
            "agents": [],
        }

    all_known_caller_numbers = list(resolution_ctx["caller_number_to_agent_id"].keys()) if include_outbound else None

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        expanded_agent_ids,
        caller_number_filters,
        include_outbound,
        accessible_agent_ids,
        all_known_caller_numbers,
    )
    query = optimize_cdr_query(query)

    records = query.all()

    handled_calls: Dict[str, Dict[str, CDRRecord]] = {}
    missed_calls: Dict[str, set] = {}
    fallback_agent_names: Dict[str, str] = {}
    attribution_diagnostics = {
        "total_records": 0,
        "attributed_records": 0,
        "unknown_records": 0,
        "unknown_rate_pct": 0,
        "attribution_sources": {
            "cc_agent": 0,
            "cc_agent_uuid": 0,
            "extension_uuid": 0,
            "caller_number": 0,
            "caller_name_exact": 0,
            "caller_name_extension": 0,
            "caller_name_fuzzy": 0,
            "raw_fallback": 0,
        },
    }

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue

        if show_attribution_diagnostics:
            attribution_diagnostics["total_records"] += 1

        agent_id, attribution_source = resolve_agent_identity(record, resolution_ctx)
        if not agent_id:
            if show_attribution_diagnostics:
                attribution_diagnostics["unknown_records"] += 1
            continue

        if requested_canonical_agent_ids and agent_id not in requested_canonical_agent_ids:
            continue

        if show_attribution_diagnostics:
            attribution_diagnostics["attributed_records"] += 1
            if attribution_source:
                attribution_diagnostics["attribution_sources"][attribution_source] += 1

        interaction_key = get_agent_interaction_key(record)
        if not interaction_key:
            continue

        if agent_id not in fallback_agent_names:
            fallback_agent_names[agent_id] = normalize_agent_name(record, agent_name_map)

        if is_handled(record):
            agent_bucket = handled_calls.setdefault(agent_id, {})
            existing = agent_bucket.get(interaction_key)
            agent_bucket[interaction_key] = choose_record(existing, record)
        elif should_count_missed_call(record, include_outbound, attribution_source) and (
            not include_outbound or has_explicit_agent_alias_match(record, expanded_agent_id_set)
        ):
            missed_calls.setdefault(agent_id, set()).add(interaction_key)

    baseline_missed_counts: Dict[str, int] = {}
    if include_outbound and show_missed_calls:
        baseline_query = apply_common_filters(
            db.query(CDRRecord),
            start_epoch,
            end_epoch,
            queue_extensions,
            expanded_agent_ids,
            caller_number_filters,
            False,
            accessible_agent_ids,
            None,
        )
        baseline_query = optimize_cdr_query(baseline_query)
        baseline_records = baseline_query.all()

        baseline_handled: Dict[str, Set[str]] = {}
        baseline_missed: Dict[str, Set[str]] = {}

        for record in baseline_records:
            if exclude_deflects and is_excluded(record):
                continue

            baseline_agent_id, _ = resolve_agent_identity(record, resolution_ctx)
            if not baseline_agent_id:
                continue

            if requested_canonical_agent_ids and baseline_agent_id not in requested_canonical_agent_ids:
                continue

            interaction_key = get_agent_interaction_key(record)
            if not interaction_key:
                continue

            if is_handled(record):
                baseline_handled.setdefault(baseline_agent_id, set()).add(interaction_key)
            elif should_count_missed_call(record, False, None):
                baseline_missed.setdefault(baseline_agent_id, set()).add(interaction_key)

        baseline_agent_ids = set(baseline_handled.keys()) | set(baseline_missed.keys())
        for baseline_agent_id in baseline_agent_ids:
            missed_keys = baseline_missed.get(baseline_agent_id, set())
            handled_keys = baseline_handled.get(baseline_agent_id, set())
            baseline_missed_counts[baseline_agent_id] = len([key for key in missed_keys if key not in handled_keys])

    agents_payload = []
    outbound_added_calls = 0
    for agent_id, calls in handled_calls.items():
        handled_records = list(calls.values())
        handled_count = len(handled_records)
        outbound_added_calls += len([
            r for r in handled_records if (getattr(r, "direction", "") or "").lower() == "outbound"
        ])
        talk_time_sec = sum((r.billsec or 0) for r in handled_records)
        aht_sec = (talk_time_sec / handled_count) if handled_count > 0 else None

        # Only include hold times > 0 (0 means not tracked by FusionPBX)
        hold_values = [r.hold_accum_seconds for r in handled_records if r.hold_accum_seconds is not None and r.hold_accum_seconds > 0]
        hold_avg_sec = (sum(hold_values) / len(hold_values)) if hold_values else None

        mos_values = [r.rtp_audio_in_mos for r in handled_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        mos_avg = (sum(mos_values) / len(mos_values)) if mos_values else 0
        mos_samples = len(mos_values)

        missed_keys = missed_calls.get(agent_id, set())
        missed_count = len([key for key in missed_keys if key not in calls]) if show_missed_calls else 0
        if include_outbound and show_missed_calls:
            missed_count = baseline_missed_counts.get(agent_id, 0)

        agent_name = agent_name_map.get(agent_id, fallback_agent_names.get(agent_id, agent_id))

        agents_payload.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "handled_calls": handled_count,
            "talk_time_sec": int(talk_time_sec),
            "aht_sec": round(aht_sec, 2) if aht_sec is not None else None,
            "hold_avg_sec": round(hold_avg_sec, 2) if hold_avg_sec is not None else None,
            "mos_avg": round(mos_avg, 2) if mos_samples else 0,
            "mos_samples": mos_samples,
            "missed_calls": missed_count,
        })

    agents_payload.sort(key=lambda item: item["handled_calls"], reverse=True)

    if show_attribution_diagnostics and attribution_diagnostics["total_records"] > 0:
        attribution_diagnostics["unknown_rate_pct"] = round(
            (attribution_diagnostics["unknown_records"] / attribution_diagnostics["total_records"]) * 100,
            2,
        )

    response_payload = {
        "start": datetime.fromtimestamp(start_epoch).isoformat(),
        "end": datetime.fromtimestamp(end_epoch).isoformat(),
        "can_view_missed_calls": show_missed_calls,
        "can_view_attribution_diagnostics": show_attribution_diagnostics,
        "outbound_added_calls": outbound_added_calls if include_outbound else 0,
        "agents": agents_payload,
    }

    if show_attribution_diagnostics:
        response_payload["attribution_diagnostics"] = attribution_diagnostics

    return response_payload


@router.get("/trends")
async def get_agent_trends(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    queues: Optional[str] = Query(None),
    agent_id: str = Query(...),
    bucket: str = Query("hour", regex="^(hour)$"),
    include_outbound: bool = Query(False),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_epoch, end_epoch = get_time_window(start, end)
    show_missed_calls = can_view_agent_missed_calls(current_user)
    queue_ids = parse_csv_list(queues)
    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys()) if queue_ids else []
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)
    resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
    requested_agent_id = canonicalize_requested_agent_id(agent_id, resolution_ctx)
    expanded_agent_ids, caller_number_filters = expand_agent_filters([requested_agent_id], resolution_ctx)
    expanded_agent_id_set = set(expanded_agent_ids)
    all_known_caller_numbers = list(resolution_ctx["caller_number_to_agent_id"].keys()) if include_outbound else None

    if queue_ids and not queue_extensions:
        return {"agent_id": agent_id, "buckets": []}

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        expanded_agent_ids,
        caller_number_filters,
        include_outbound,
        accessible_agent_ids,
        all_known_caller_numbers,
    )
    query = optimize_cdr_query(query)

    records = query.all()
    buckets: Dict[str, Dict[str, Dict[str, CDRRecord]]] = {}
    missed_buckets: Dict[str, set] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue

        resolved_agent_id, attribution_source = resolve_agent_identity(record, resolution_ctx)
        if resolved_agent_id != requested_agent_id:
            continue

        interaction_key = get_agent_interaction_key(record)
        if not interaction_key:
            continue

        bucket_start = datetime.fromtimestamp(record.start_epoch)
        bucket_start = bucket_start.replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_start.isoformat()

        if is_handled(record):
            bucket_map = buckets.setdefault(bucket_key, {})
            existing = bucket_map.get(interaction_key)
            bucket_map[interaction_key] = choose_record(existing, record)
        elif should_count_missed_call(record, include_outbound, attribution_source) and (
            not include_outbound or has_explicit_agent_alias_match(record, expanded_agent_id_set)
        ):
            missed_buckets.setdefault(bucket_key, set()).add(interaction_key)

    payload = []
    for bucket_key in sorted(buckets.keys()):
        handled_records = list(buckets[bucket_key].values())
        handled_count = len(handled_records)
        talk_time_sec = sum((r.billsec or 0) for r in handled_records)
        aht_sec = (talk_time_sec / handled_count) if handled_count > 0 else 0
        mos_values = [r.rtp_audio_in_mos for r in handled_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        mos_avg = (sum(mos_values) / len(mos_values)) if mos_values else None

        missed_keys = missed_buckets.get(bucket_key, set())
        missed_count = len([key for key in missed_keys if key not in buckets[bucket_key]]) if show_missed_calls else 0

        payload.append({
            "bucket_start": bucket_key,
            "handled_calls": handled_count,
            "talk_time_sec": int(talk_time_sec),
            "aht_sec": round(aht_sec, 2),
            "mos_avg": round(mos_avg, 2) if mos_avg is not None else None,
            "missed_calls": missed_count,
        })

    return {
        "agent_id": agent_id,
        "can_view_missed_calls": show_missed_calls,
        "buckets": payload,
    }


@router.get("/report")
async def get_agent_performance_report(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    queues: Optional[str] = Query(None),
    agents: Optional[str] = Query(None),
    include_outbound: bool = Query(False),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_epoch, end_epoch = get_time_window(start, end)
    show_missed_calls = can_view_agent_missed_calls(current_user)
    queue_ids = parse_csv_list(queues)
    agent_ids = parse_csv_list(agents)
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    queue_lookup = build_queue_lookup(db, queue_ids)
    queue_extensions = list(queue_lookup.keys()) if queue_ids else []
    resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
    agent_name_map: Dict[str, str] = resolution_ctx["agent_name_map"]  # type: ignore[assignment]
    expanded_agent_ids, caller_number_filters = expand_agent_filters(agent_ids, resolution_ctx)
    expanded_agent_id_set = set(expanded_agent_ids)
    alias_to_agent_id: Dict[str, str] = resolution_ctx["alias_to_agent_id"]  # type: ignore[assignment]
    requested_canonical_agent_ids: Set[str] = {
        alias_to_agent_id.get(agent_id, agent_id)
        for agent_id in agent_ids
        if agent_id
    }
    all_known_caller_numbers = list(resolution_ctx["caller_number_to_agent_id"].keys()) if include_outbound else None

    if queue_ids and not queue_extensions:
        return {
            "start": datetime.fromtimestamp(start_epoch).isoformat(),
            "end": datetime.fromtimestamp(end_epoch).isoformat(),
            "queues": [],
            "agents": [],
        }

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        expanded_agent_ids,
        caller_number_filters,
        include_outbound,
        accessible_agent_ids,
        all_known_caller_numbers,
    )
    if not include_outbound:
        query = query.filter(CDRRecord.cc_queue.isnot(None))
    query = optimize_cdr_query(query)

    records = query.all()

    handled_calls = defaultdict(dict)
    handled_by_queue = defaultdict(lambda: defaultdict(dict))
    missed_calls = defaultdict(set)
    missed_by_queue = defaultdict(lambda: defaultdict(set))
    fallback_agent_names: Dict[str, str] = {}
    queue_meta: Dict[str, str] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue

        agent_id, attribution_source = resolve_agent_identity(record, resolution_ctx)
        if not agent_id:
            continue

        if requested_canonical_agent_ids and agent_id not in requested_canonical_agent_ids:
            continue

        interaction_key = get_agent_interaction_key(record)
        if not interaction_key:
            continue

        if agent_id not in fallback_agent_names:
            fallback_agent_names[agent_id] = normalize_agent_name(record, agent_name_map)

        queue_info = resolve_queue_key(record, queue_lookup)
        if not queue_info:
            # Outbound calls have no queue; include them in agent totals only
            if include_outbound and (getattr(record, "direction", "") or "").lower() == "outbound":
                if is_handled(record):
                    agent_bucket = handled_calls[agent_id]
                    agent_bucket[interaction_key] = choose_record(agent_bucket.get(interaction_key), record)
            continue

        queue_id = queue_info["queue_id"]
        queue_name = queue_info["queue_name"]
        queue_meta[queue_id] = queue_name

        if is_handled(record):
            agent_bucket = handled_calls[agent_id]
            agent_bucket[interaction_key] = choose_record(agent_bucket.get(interaction_key), record)

            queue_bucket = handled_by_queue[agent_id][queue_id]
            queue_bucket[interaction_key] = choose_record(queue_bucket.get(interaction_key), record)
        elif should_count_missed_call(record, include_outbound, attribution_source) and (
            not include_outbound or has_explicit_agent_alias_match(record, expanded_agent_id_set)
        ):
            missed_calls[agent_id].add(interaction_key)
            missed_by_queue[agent_id][queue_id].add(interaction_key)

    baseline_missed_counts: Dict[str, int] = {}
    baseline_queue_missed_counts: Dict[str, Dict[str, int]] = {}
    if include_outbound and show_missed_calls:
        baseline_query = apply_common_filters(
            db.query(CDRRecord),
            start_epoch,
            end_epoch,
            queue_extensions,
            expanded_agent_ids,
            caller_number_filters,
            False,
            accessible_agent_ids,
            None,
        ).filter(CDRRecord.cc_queue.isnot(None))
        baseline_query = optimize_cdr_query(baseline_query)
        baseline_records = baseline_query.all()

        baseline_handled: Dict[str, Set[str]] = defaultdict(set)
        baseline_handled_by_queue: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        baseline_missed: Dict[str, Set[str]] = defaultdict(set)
        baseline_missed_by_queue: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

        for record in baseline_records:
            if exclude_deflects and is_excluded(record):
                continue

            baseline_agent_id, _ = resolve_agent_identity(record, resolution_ctx)
            if not baseline_agent_id:
                continue

            if requested_canonical_agent_ids and baseline_agent_id not in requested_canonical_agent_ids:
                continue

            interaction_key = get_agent_interaction_key(record)
            if not interaction_key:
                continue

            queue_info = resolve_queue_key(record, queue_lookup)
            if not queue_info:
                continue

            queue_id = queue_info["queue_id"]

            if is_handled(record):
                baseline_handled[baseline_agent_id].add(interaction_key)
                baseline_handled_by_queue[baseline_agent_id][queue_id].add(interaction_key)
            elif should_count_missed_call(record, False, None):
                baseline_missed[baseline_agent_id].add(interaction_key)
                baseline_missed_by_queue[baseline_agent_id][queue_id].add(interaction_key)

        for baseline_agent_id in (set(baseline_handled.keys()) | set(baseline_missed.keys())):
            missed_keys = baseline_missed.get(baseline_agent_id, set())
            handled_keys = baseline_handled.get(baseline_agent_id, set())
            baseline_missed_counts[baseline_agent_id] = len([key for key in missed_keys if key not in handled_keys])

            queue_counts: Dict[str, int] = {}
            queue_ids_for_agent = set(baseline_handled_by_queue[baseline_agent_id].keys()) | set(baseline_missed_by_queue[baseline_agent_id].keys())
            for queue_id in queue_ids_for_agent:
                queue_missed_keys = baseline_missed_by_queue[baseline_agent_id].get(queue_id, set())
                queue_handled_keys = baseline_handled_by_queue[baseline_agent_id].get(queue_id, set())
                queue_counts[queue_id] = len([key for key in queue_missed_keys if key not in queue_handled_keys])
            baseline_queue_missed_counts[baseline_agent_id] = queue_counts

    queue_payload = []
    for queue_extension, queue in sorted(queue_lookup.items(), key=lambda item: (item[1].name or "")):
        queue_id = str(queue.queue_id)
        queue_name = queue.name
        queue_payload.append({"queue_id": queue_id, "queue_name": queue_name})
        queue_meta.setdefault(queue_id, queue_name)

    for queue_id in sorted(queue_meta.keys(), key=lambda key: (queue_meta[key] or "").lower()):
        if any(entry["queue_id"] == queue_id for entry in queue_payload):
            continue
        queue_payload.append({"queue_id": queue_id, "queue_name": queue_meta[queue_id]})

    agents_payload = []
    agent_id_set = set(handled_calls.keys()) | set(missed_calls.keys())

    for agent_id in agent_id_set:
        handled_records = list(handled_calls.get(agent_id, {}).values())
        handled_count = len(handled_records)
        talk_time_sec = sum((r.billsec or 0) for r in handled_records)
        aht_sec = (talk_time_sec / handled_count) if handled_count > 0 else None

        missed_keys = missed_calls.get(agent_id, set())
        missed_count = len([key for key in missed_keys if key not in handled_calls.get(agent_id, {})]) if show_missed_calls else 0
        if include_outbound and show_missed_calls:
            missed_count = baseline_missed_counts.get(agent_id, 0)

        queue_metrics = {}
        queue_keys = set(handled_by_queue.get(agent_id, {}).keys()) | set(missed_by_queue.get(agent_id, {}).keys())
        for queue_id in queue_keys:
            queue_handled_records = list(handled_by_queue[agent_id][queue_id].values())
            queue_handled_count = len(queue_handled_records)
            queue_talk_time = sum((r.billsec or 0) for r in queue_handled_records)
            queue_missed_keys = missed_by_queue[agent_id].get(queue_id, set())
            queue_missed_count = len([
                key for key in queue_missed_keys if key not in handled_by_queue[agent_id][queue_id]
            ]) if show_missed_calls else 0
            if include_outbound and show_missed_calls:
                queue_missed_count = baseline_queue_missed_counts.get(agent_id, {}).get(queue_id, 0)

            queue_metrics[queue_id] = {
                "handled_calls": queue_handled_count,
                "talk_time_sec": int(queue_talk_time),
                "missed_calls": queue_missed_count,
            }

        agent_name = agent_name_map.get(agent_id, fallback_agent_names.get(agent_id, agent_id))

        agents_payload.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "handled_calls": handled_count,
            "talk_time_sec": int(talk_time_sec),
            "aht_sec": round(aht_sec, 2) if aht_sec is not None else None,
            "missed_calls": missed_count,
            "queues": queue_metrics,
        })

    agents_payload.sort(key=lambda item: item["handled_calls"], reverse=True)

    return {
        "start": datetime.fromtimestamp(start_epoch).isoformat(),
        "end": datetime.fromtimestamp(end_epoch).isoformat(),
        "can_view_missed_calls": show_missed_calls,
        "queues": queue_payload,
        "agents": agents_payload,
    }


@router.get("/outliers")
async def get_agent_outliers(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    queues: Optional[str] = Query(None),
    agent_id: str = Query(...),
    type: str = Query("long_calls", regex="^(long_calls|low_mos)$"),
    limit: int = Query(50, ge=1, le=200),
    include_outbound: bool = Query(False),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_epoch, end_epoch = get_time_window(start, end)
    queue_ids = parse_csv_list(queues)
    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys()) if queue_ids else []
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)
    resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
    requested_agent_id = canonicalize_requested_agent_id(agent_id, resolution_ctx)
    expanded_agent_ids, caller_number_filters = expand_agent_filters([requested_agent_id], resolution_ctx)
    all_known_caller_numbers = list(resolution_ctx["caller_number_to_agent_id"].keys()) if include_outbound else None

    if queue_ids and not queue_extensions:
        return {"agent_id": agent_id, "type": type, "outliers": []}

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        expanded_agent_ids,
        caller_number_filters,
        include_outbound,
        accessible_agent_ids,
        all_known_caller_numbers,
    )
    query = optimize_cdr_query(query)

    records = query.all()
    handled_by_key: Dict[str, CDRRecord] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue
        if resolve_agent_id(record, resolution_ctx) != requested_agent_id:
            continue
        if not is_handled(record):
            continue
        call_key = get_call_key(record)
        if not call_key:
            continue
        handled_by_key[call_key] = choose_record(handled_by_key.get(call_key), record)

    handled_records = list(handled_by_key.values())

    if type == "low_mos":
        handled_records = [r for r in handled_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        handled_records.sort(key=lambda r: r.rtp_audio_in_mos)
    else:
        handled_records.sort(key=lambda r: r.billsec or 0, reverse=True)

    outliers = []
    for record in handled_records[:limit]:
        outliers.append({
            "call_id": record.xml_cdr_uuid,
            "start_time": datetime.fromtimestamp(record.start_epoch).isoformat(),
            "queue": normalize_queue_name(record, queue_name_map),
            "caller_id": record.caller_id_number,
            "billsec": record.billsec or 0,
            "mos": record.rtp_audio_in_mos,
            "hangup_cause": record.hangup_cause,
        })

    return {
        "agent_id": agent_id,
        "type": type,
        "outliers": outliers,
    }


@router.get("/calls")
async def get_agent_calls(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    queues: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("start_epoch"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    hangup_cause: Optional[str] = Query(None),
    missed_only: bool = Query(False),
    include_outbound: bool = Query(False),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_epoch, end_epoch = get_time_window(start, end)
    show_missed_calls = can_view_agent_missed_calls(current_user)
    queue_ids = parse_csv_list(queues)
    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys()) if queue_ids else []
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    if queue_ids and not queue_extensions:
        return {"total": 0, "limit": limit, "offset": offset, "calls": []}

    agent_ids = [agent_id] if agent_id else []
    resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
    expanded_agent_ids, caller_number_filters = expand_agent_filters(agent_ids, resolution_ctx)
    requested_agent_id = None
    if agent_id:
        requested_agent_id = canonicalize_requested_agent_id(agent_id, resolution_ctx)
    all_known_caller_numbers = list(resolution_ctx["caller_number_to_agent_id"].keys()) if include_outbound else None

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        expanded_agent_ids,
        caller_number_filters,
        include_outbound,
        accessible_agent_ids,
        all_known_caller_numbers,
    )
    query = optimize_cdr_query(query)

    if search:
        query = query.filter(CDRRecord.caller_id_number.ilike(f"%{search}%"))
    if hangup_cause:
        query = query.filter(CDRRecord.hangup_cause == hangup_cause)

    if sort == "billsec":
        sort_column = CDRRecord.billsec
    elif sort == "mos":
        sort_column = CDRRecord.rtp_audio_in_mos
    else:
        sort_column = CDRRecord.start_epoch

    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    records = query.all()
    filtered = []
    for record in records:
        if exclude_deflects and is_excluded(record):
            continue
        is_record_missed = is_missed(record)
        if missed_only and show_missed_calls and not is_record_missed:
            continue
        resolved_id = resolve_agent_id(record, resolution_ctx)
        if agent_id and resolved_id != requested_agent_id:
            continue
        filtered.append(record)

    total = len(filtered)
    paged = filtered[offset: offset + limit]

    calls_payload = []
    for record in paged:
        is_record_missed = is_missed(record)
        result_value = "missed" if is_record_missed else ("answered" if is_handled(record) else "other")
        if not show_missed_calls and result_value == "missed":
            result_value = "other"

        calls_payload.append({
            "call_id": record.xml_cdr_uuid,
            "start_time": datetime.fromtimestamp(record.start_epoch).isoformat(),
            "queue": normalize_queue_name(record, queue_name_map),
            "caller_id": record.caller_id_number,
            "result": result_value,
            "talk_time_sec": record.billsec or 0,
            "aht_sec": record.billsec or 0,
            "mos": record.rtp_audio_in_mos,
            "hangup_cause": record.hangup_cause,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "calls": calls_payload,
    }


@router.get("/calls/{call_uuid}")
async def get_agent_call_detail(
    call_uuid: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(CDRRecord).filter(CDRRecord.xml_cdr_uuid == call_uuid).first()
    if not record:
        raise HTTPException(status_code=404, detail="Call not found")

    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)
    if accessible_agent_ids is not None:
        record_agent = normalize_agent_id(record)
        if not record_agent or record_agent not in accessible_agent_ids:
            raise HTTPException(status_code=404, detail="Call not found")

    return {
        "call_id": record.xml_cdr_uuid,
        "start_time": datetime.fromtimestamp(record.start_epoch).isoformat() if record.start_epoch else None,
        "answer_time": datetime.fromtimestamp(record.answer_epoch).isoformat() if record.answer_epoch else None,
        "end_time": datetime.fromtimestamp(record.end_epoch).isoformat() if record.end_epoch else None,
        "direction": record.direction,
        "queue": record.cc_queue,
        "agent_uuid": record.cc_agent_uuid,
        "agent": record.cc_agent,
        "caller_id_name": record.caller_id_name,
        "caller_id_number": record.caller_id_number,
        "destination_number": record.destination_number,
        "duration": record.duration,
        "billsec": record.billsec,
        "hold_accum_seconds": record.hold_accum_seconds,
        "rtp_audio_in_mos": record.rtp_audio_in_mos,
        "hangup_cause": record.hangup_cause,
        "sip_hangup_disposition": record.sip_hangup_disposition,
        "cc_queue_joined_epoch": record.cc_queue_joined_epoch,
        "cc_queue_answered_epoch": record.cc_queue_answered_epoch,
        "cc_queue_terminated_epoch": record.cc_queue_terminated_epoch,
        "cc_queue_canceled_epoch": record.cc_queue_canceled_epoch,
        "cc_cancel_reason": record.cc_cancel_reason,
        "cc_cause": record.cc_cause,
        "cc_agent_type": record.cc_agent_type,
        "cc_agent_bridged": record.cc_agent_bridged,
        "cc_side": record.cc_side,
        "cc_member_uuid": record.cc_member_uuid,
        "bridge_uuid": record.bridge_uuid,
        "leg": record.leg,
        "last_app": record.last_app,
        "call_disposition": record.call_disposition,
    }
