"""
Agent performance API routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import or_, desc
from sqlalchemy.orm import Session, load_only

from app.auth import get_current_user
from app.database import get_db
from app.models import CDRRecord, Queue, Agent, Extension
from app.utils.agent_performance_utils import (
    normalize_agent_id,
    normalize_agent_name,
    normalize_queue_name,
    get_call_key,
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
    include_outbound: bool,
    accessible_agent_ids: Optional[Set[str]] = None,
):
    query = query.filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
    )

    if not include_outbound:
        query = query.filter(CDRRecord.direction == "inbound")

    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        query = query.filter(or_(*extension_filters))

    if agent_ids:
        query = query.filter(
            or_(
                CDRRecord.cc_agent_uuid.in_(agent_ids),
                CDRRecord.cc_agent.in_(agent_ids),
                CDRRecord.extension_uuid.in_(agent_ids),
            )
        )

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

    query = query.filter(
        or_(
            CDRRecord.cc_agent_uuid.isnot(None),
            CDRRecord.cc_agent.isnot(None),
            CDRRecord.extension_uuid.isnot(None),
        )
    )

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
    queue_ids = parse_csv_list(queues)
    agent_ids = parse_csv_list(agents)
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys())
    # Include all agents (even disabled) for historical name resolution
    agent_name_map = build_agent_name_map(db, enabled_only=False)

    if queue_ids and not queue_extensions:
        return {
            "start": datetime.fromtimestamp(start_epoch).isoformat(),
            "end": datetime.fromtimestamp(end_epoch).isoformat(),
            "agents": [],
        }

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        agent_ids,
        include_outbound,
        accessible_agent_ids,
    )
    query = optimize_cdr_query(query)

    records = query.all()

    handled_calls: Dict[str, Dict[str, CDRRecord]] = {}
    missed_calls: Dict[str, set] = {}
    fallback_agent_names: Dict[str, str] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue

        agent_id = normalize_agent_id(record)
        if not agent_id:
            continue

        call_key = get_call_key(record)
        if not call_key:
            continue

        if agent_id not in fallback_agent_names:
            fallback_agent_names[agent_id] = normalize_agent_name(record, agent_name_map)

        if is_handled(record):
            agent_bucket = handled_calls.setdefault(agent_id, {})
            existing = agent_bucket.get(call_key)
            agent_bucket[call_key] = choose_record(existing, record)
        elif is_missed(record):
            missed_calls.setdefault(agent_id, set()).add(call_key)

    agents_payload = []
    for agent_id, calls in handled_calls.items():
        handled_records = list(calls.values())
        handled_count = len(handled_records)
        talk_time_sec = sum((r.billsec or 0) for r in handled_records)
        aht_sec = (talk_time_sec / handled_count) if handled_count > 0 else None

        # Only include hold times > 0 (0 means not tracked by FusionPBX)
        hold_values = [r.hold_accum_seconds for r in handled_records if r.hold_accum_seconds is not None and r.hold_accum_seconds > 0]
        hold_avg_sec = (sum(hold_values) / len(hold_values)) if hold_values else None

        mos_values = [r.rtp_audio_in_mos for r in handled_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        mos_avg = (sum(mos_values) / len(mos_values)) if mos_values else 0
        mos_samples = len(mos_values)

        missed_keys = missed_calls.get(agent_id, set())
        missed_count = len([key for key in missed_keys if key not in calls])

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

    return {
        "start": datetime.fromtimestamp(start_epoch).isoformat(),
        "end": datetime.fromtimestamp(end_epoch).isoformat(),
        "agents": agents_payload,
    }


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
    queue_ids = parse_csv_list(queues)
    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys())
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    if queue_ids and not queue_extensions:
        return {"agent_id": agent_id, "buckets": []}

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        [agent_id],
        include_outbound,
        accessible_agent_ids,
    )
    query = optimize_cdr_query(query)

    records = query.all()
    buckets: Dict[str, Dict[str, Dict[str, CDRRecord]]] = {}
    missed_buckets: Dict[str, set] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue

        if normalize_agent_id(record) != agent_id:
            continue

        call_key = get_call_key(record)
        if not call_key:
            continue

        bucket_start = datetime.fromtimestamp(record.start_epoch)
        bucket_start = bucket_start.replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_start.isoformat()

        if is_handled(record):
            bucket_map = buckets.setdefault(bucket_key, {})
            existing = bucket_map.get(call_key)
            bucket_map[call_key] = choose_record(existing, record)
        elif is_missed(record):
            missed_buckets.setdefault(bucket_key, set()).add(call_key)

    payload = []
    for bucket_key in sorted(buckets.keys()):
        handled_records = list(buckets[bucket_key].values())
        handled_count = len(handled_records)
        talk_time_sec = sum((r.billsec or 0) for r in handled_records)
        aht_sec = (talk_time_sec / handled_count) if handled_count > 0 else 0
        mos_values = [r.rtp_audio_in_mos for r in handled_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        mos_avg = (sum(mos_values) / len(mos_values)) if mos_values else None

        missed_keys = missed_buckets.get(bucket_key, set())
        missed_count = len([key for key in missed_keys if key not in buckets[bucket_key]])

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
    queue_ids = parse_csv_list(queues)
    agent_ids = parse_csv_list(agents)
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    queue_lookup = build_queue_lookup(db, queue_ids)
    queue_extensions = list(queue_lookup.keys())
    agent_name_map = build_agent_name_map(db, enabled_only=False)

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
        agent_ids,
        include_outbound,
        accessible_agent_ids,
    ).filter(CDRRecord.cc_queue.isnot(None))
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

        agent_id = normalize_agent_id(record)
        if not agent_id:
            continue

        call_key = get_call_key(record)
        if not call_key:
            continue

        if agent_id not in fallback_agent_names:
            fallback_agent_names[agent_id] = normalize_agent_name(record, agent_name_map)

        queue_info = resolve_queue_key(record, queue_lookup)
        if not queue_info:
            continue

        queue_id = queue_info["queue_id"]
        queue_name = queue_info["queue_name"]
        queue_meta[queue_id] = queue_name

        if is_handled(record):
            agent_bucket = handled_calls[agent_id]
            agent_bucket[call_key] = choose_record(agent_bucket.get(call_key), record)

            queue_bucket = handled_by_queue[agent_id][queue_id]
            queue_bucket[call_key] = choose_record(queue_bucket.get(call_key), record)
        elif is_missed(record):
            missed_calls[agent_id].add(call_key)
            missed_by_queue[agent_id][queue_id].add(call_key)

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
        missed_count = len([key for key in missed_keys if key not in handled_calls.get(agent_id, {})])

        queue_metrics = {}
        queue_keys = set(handled_by_queue.get(agent_id, {}).keys()) | set(missed_by_queue.get(agent_id, {}).keys())
        for queue_id in queue_keys:
            queue_handled_records = list(handled_by_queue[agent_id][queue_id].values())
            queue_handled_count = len(queue_handled_records)
            queue_talk_time = sum((r.billsec or 0) for r in queue_handled_records)
            queue_missed_keys = missed_by_queue[agent_id].get(queue_id, set())
            queue_missed_count = len([
                key for key in queue_missed_keys if key not in handled_by_queue[agent_id][queue_id]
            ])

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
    queue_extensions = list(queue_name_map.keys())
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    if queue_ids and not queue_extensions:
        return {"agent_id": agent_id, "type": type, "outliers": []}

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        [agent_id],
        include_outbound,
        accessible_agent_ids,
    )
    query = optimize_cdr_query(query)

    records = query.all()
    handled_by_key: Dict[str, CDRRecord] = {}

    for record in records:
        if exclude_deflects and is_excluded(record):
            continue
        if normalize_agent_id(record) != agent_id:
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
    queue_ids = parse_csv_list(queues)
    queue_name_map = build_queue_extension_map(db, queue_ids)
    queue_extensions = list(queue_name_map.keys())
    accessible_agent_ids = get_accessible_agent_identifiers(db, current_user)

    if queue_ids and not queue_extensions:
        return {"total": 0, "limit": limit, "offset": offset, "calls": []}

    agent_ids = [agent_id] if agent_id else []

    query = apply_common_filters(
        db.query(CDRRecord),
        start_epoch,
        end_epoch,
        queue_extensions,
        agent_ids,
        include_outbound,
        accessible_agent_ids,
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
        if missed_only and not is_missed(record):
            continue
        if agent_id and normalize_agent_id(record) != agent_id:
            continue
        filtered.append(record)

    total = len(filtered)
    paged = filtered[offset: offset + limit]

    calls_payload = []
    for record in paged:
        calls_payload.append({
            "call_id": record.xml_cdr_uuid,
            "start_time": datetime.fromtimestamp(record.start_epoch).isoformat(),
            "queue": normalize_queue_name(record, queue_name_map),
            "caller_id": record.caller_id_number,
            "result": "missed" if is_missed(record) else ("answered" if is_handled(record) else "other"),
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
