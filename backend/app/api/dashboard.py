"""
API routes for dashboard data
"""
import re
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, case, desc, or_, cast, String
from app.database import get_db
from app.models import CDRRecord, Queue, Agent, DailyAggregate, HourlyAggregate, User, Extension
from app.auth import get_current_user
from app.schemas import ExecutiveOverviewResponse, QueuePerformanceResponse, AgentPerformanceResponse, RepeatCallersResponse
from app.kpi_definitions import KPIDefinitions
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List, Optional, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def to_sunday_first_weekday_index(python_weekday: int) -> int:
    """Convert Python weekday numbering (Mon=0..Sun=6) to Sunday-first (Sun=0..Sat=6)."""
    return (python_weekday + 1) % 7


def get_requested_timezone(timezone_name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "America/Phoenix")
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone: {timezone_name}") from exc


def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def local_timestamp_expr(epoch_column, timezone_name: str):
    return func.timezone(timezone_name, func.to_timestamp(epoch_column))


def get_accessible_agent_identifiers(db: Session, current_user: dict) -> Optional[Set[str]]:
    """Return allowed agent identifiers for the current user.

    Visibility restrictions were removed, so all authenticated users share the same scope.
    """
    return None


@router.get("/queues-visible")
async def get_visible_queues(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get queue metadata visible to current user"""
    queues = db.query(Queue).order_by(Queue.name).all()
    return queues


@router.get("/agents-visible")
async def get_visible_agents(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get agent metadata visible to current user."""
    agents = db.query(Agent).order_by(Agent.agent_name).all()
    return agents


@router.get("/executive-overview")
async def get_executive_overview(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_ids: Optional[List[str]] = Query(None),
    direction: Optional[str] = Query(None),
    timezone: str = Query("America/Phoenix"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get executive overview dashboard data
    
    Includes:
    - KPI strip (Offered, Answer Rate, etc.)
    - Trend charts
    - Ranked tables
    """
    
    user_timezone = get_requested_timezone(timezone)
    
    # Default to last 7 days if not specified
    if not end_date:
        end_date = datetime.now(user_timezone)
    if not start_date:
        start_date = end_date - timedelta(days=7)

    start_date = ensure_utc_datetime(start_date)
    end_date = ensure_utc_datetime(end_date)
    
    start_epoch = int(start_date.timestamp())
    end_epoch = int(end_date.timestamp())
    
    # Convert queue UUIDs to cc_queue identifiers (extension@context format)
    # Since queue_context may be NULL, we'll filter using just the extension part
    queue_extensions = None
    if queue_ids:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
        queue_extensions = [q.queue_extension for q in queues if q.queue_extension]
    
    # Query base CDR data
    base_query = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
    )
    
    if queue_extensions:
        # Filter by matching the extension part of cc_queue (before @)
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        base_query = base_query.filter(or_(*extension_filters))
    
    if direction:
        base_query = base_query.filter(CDRRecord.direction == direction)
    
    # Calculate KPIs
    # Note: Counting methodology to match FusionPBX queue statistics
    # We count distinct (caller_id_number, cc_queue_joined_epoch) pairs to identify unique queue entries
    # This groups multiple CDR legs (transfers, races, etc.) that belong to the same queue interaction
    
    total_inbound = base_query.filter(CDRRecord.direction == 'inbound').count()
    
    # Get all records that joined the queue for detailed analysis
    queue_records_query = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None)
    )
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        queue_records_query = queue_records_query.filter(or_(*extension_filters))
    if direction:
        queue_records_query = queue_records_query.filter(CDRRecord.direction == direction)
    
    queue_records = queue_records_query.all()
    
    # Group by unique queue entries (caller + join time)
    unique_queue_entries = {}
    for record in queue_records:
        key = (record.caller_id_number, record.cc_queue_joined_epoch)
        if key not in unique_queue_entries:
            unique_queue_entries[key] = []
        unique_queue_entries[key].append(record)
    
    # Helper function to determine if a queue entry is truly abandoned
    def is_true_abandoned(records):
        """
        Determine if a group of CDR records representing a single queue entry
        is a true abandoned call based on FusionPBX logic.
        """
        # If any record was answered, not abandoned
        if any(r.cc_queue_answered_epoch is not None for r in records):
            return False
        
        # Check if any record matches abandoned criteria
        for record in records:
            # Must have billsec = 0
            if (record.billsec or 0) != 0:
                continue
            
            # Exclude deflects and blind transfers
            if (getattr(record, 'last_app', None) or '') == 'deflect':
                continue
            if (record.hangup_cause or '') == 'BLIND_TRANSFER':
                continue
            
            # Must show caller-abandoned behavior
            if (record.hangup_cause in ('ORIGINATOR_CANCEL', 'NO_ANSWER') or
                (getattr(record, 'cc_cause', None) or '') == 'TIMEOUT' or
                (getattr(record, 'call_disposition', None) or '') == 'missed'):
                return True
        
        return False
    
    # Count outcomes
    total_offered_queue = len(unique_queue_entries)
    total_answered = sum(1 for records in unique_queue_entries.values() 
                        if any(r.cc_queue_answered_epoch is not None for r in records))
    total_abandoned = sum(1 for records in unique_queue_entries.values()
                         if is_true_abandoned(records))
    
    # Verify counts add up
    other = total_offered_queue - total_answered - total_abandoned
    if other > 0:
        print(f"WARNING: {other} calls are neither answered nor abandoned (may have no queue data)")
    
    print(f"Total queue entries: {total_offered_queue} (answered: {total_answered}, abandoned: {total_abandoned})")
    
    answer_rate = (total_answered / total_offered_queue * 100) if total_offered_queue > 0 else 0
    abandon_rate = (total_abandoned / total_offered_queue * 100) if total_offered_queue > 0 else 0
    
    print(f"Calculated answer_rate: {answer_rate}%")
    print(f"Calculated abandon_rate: {abandon_rate}%")
    print(f"Sum: {answer_rate + abandon_rate}%")
    
    # Core aggregates (DB-side for performance)
    avg_asa = base_query.filter(
        CDRRecord.cc_queue_answered_epoch.isnot(None),
        CDRRecord.cc_queue_joined_epoch.isnot(None),
    ).with_entities(
        func.avg(CDRRecord.cc_queue_answered_epoch - CDRRecord.cc_queue_joined_epoch)
    ).scalar() or 0

    avg_aht = base_query.filter(
        CDRRecord.cc_queue_answered_epoch.isnot(None),
        CDRRecord.cc_queue_joined_epoch.isnot(None),
    ).with_entities(
        func.avg(CDRRecord.billsec)
    ).scalar() or 0

    avg_mos = base_query.filter(
        CDRRecord.rtp_audio_in_mos > 0,
    ).with_entities(
        func.avg(CDRRecord.rtp_audio_in_mos)
    ).scalar() or 0

    total_talk_time = base_query.with_entities(
        func.coalesce(func.sum(CDRRecord.billsec), 0)
    ).scalar() or 0

    # Service level (default 30s)
    threshold = 30
    service_level_total = base_query.filter(
        CDRRecord.cc_queue_answered_epoch.isnot(None),
        CDRRecord.cc_queue_joined_epoch.isnot(None),
    ).with_entities(
        func.count()
    ).scalar() or 0
    service_level_within = base_query.filter(
        CDRRecord.cc_queue_answered_epoch.isnot(None),
        CDRRecord.cc_queue_joined_epoch.isnot(None),
        (CDRRecord.cc_queue_answered_epoch - CDRRecord.cc_queue_joined_epoch) <= threshold,
    ).with_entities(
        func.count()
    ).scalar() or 0
    service_level = (service_level_within / service_level_total * 100) if service_level_total > 0 else 0
    
    # Get trend data (daily) - count unique queue entries by (caller, join_epoch)
    local_start_timestamp = local_timestamp_expr(CDRRecord.start_epoch, timezone)
    trend_query = db.query(
        func.date(local_start_timestamp).label('date'),
        # Count distinct (caller + join_epoch) combinations
        func.count(func.distinct(
            func.concat(CDRRecord.caller_id_number, '|', cast(CDRRecord.cc_queue_joined_epoch, String))
        )).label('offered'),
        # Count answered queue entries  
        func.count(func.distinct(
            case(
                (CDRRecord.cc_queue_answered_epoch.isnot(None), 
                 func.concat(CDRRecord.caller_id_number, '|', cast(CDRRecord.cc_queue_joined_epoch, String))),
                else_=None
            )
        )).label('answered'),
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None)
    )
    
    # Apply same filters as main query
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        trend_query = trend_query.filter(or_(*extension_filters))
    if direction:
        trend_query = trend_query.filter(CDRRecord.direction == direction)
    
    daily_aggregates = trend_query.group_by('date').order_by('date').all()
    
    offered_trend = [{'date': str(d[0]), 'value': d[1]} for d in daily_aggregates]
    answered_trend = [{'date': str(d[0]), 'value': d[2] or 0} for d in daily_aggregates]

    # Bucket call volume by weekday and hour using the same unique queue-entry methodology
    weekday_totals = {index: 0 for index in range(7)}
    hour_totals = {index: 0 for index in range(24)}

    for records in unique_queue_entries.values():
        record = records[0]
        queue_epoch = record.cc_queue_joined_epoch or record.start_epoch
        if queue_epoch is None:
            continue

        bucket_dt = datetime.fromtimestamp(queue_epoch, user_timezone)
        weekday_index = to_sunday_first_weekday_index(bucket_dt.weekday())
        weekday_totals[weekday_index] += 1
        hour_totals[bucket_dt.hour] += 1

    date_cursor = start_date.astimezone(user_timezone).date()
    end_date_only = end_date.astimezone(user_timezone).date()
    weekday_occurrences = {index: 0 for index in range(7)}
    total_days_in_range = 0

    while date_cursor <= end_date_only:
        weekday_index = to_sunday_first_weekday_index(date_cursor.weekday())
        weekday_occurrences[weekday_index] += 1
        total_days_in_range += 1
        date_cursor += timedelta(days=1)

    weekday_call_volume_buckets = []
    for weekday_index, weekday_label in enumerate(WEEKDAY_LABELS):
        occurrences = weekday_occurrences[weekday_index]
        total_calls = weekday_totals[weekday_index]
        average_calls = (total_calls / occurrences) if occurrences > 0 else 0
        weekday_call_volume_buckets.append({
            'bucket': weekday_label,
            'sortOrder': weekday_index,
            'totalCalls': total_calls,
            'averageCalls': round(average_calls, 2),
            'occurrences': occurrences,
        })

    hour_call_volume_buckets = []
    for hour_index in range(24):
        total_calls = hour_totals[hour_index]
        average_calls = (total_calls / total_days_in_range) if total_days_in_range > 0 else 0
        hour_call_volume_buckets.append({
            'bucket': f'{hour_index:02d}:00',
            'sortOrder': hour_index,
            'totalCalls': total_calls,
            'averageCalls': round(average_calls, 2),
            'occurrences': total_days_in_range,
        })
    
    # Get service level trend (daily)
    service_level_trend_query = db.query(
        func.date(local_start_timestamp).label('date'),
        func.count(func.distinct(
            case(
                ((CDRRecord.cc_queue_answered_epoch - CDRRecord.cc_queue_joined_epoch) <= 30,
                 func.concat(CDRRecord.caller_id_number, '|', cast(CDRRecord.cc_queue_joined_epoch, String))),
                else_=None
            )
        )).label('within_threshold'),
        func.count(func.distinct(
            case(
                (CDRRecord.cc_queue_answered_epoch.isnot(None),
                 func.concat(CDRRecord.caller_id_number, '|', cast(CDRRecord.cc_queue_joined_epoch, String))),
                else_=None
            )
        )).label('total_answered'),
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None),
        CDRRecord.cc_queue_answered_epoch.isnot(None)
    )
    
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        service_level_trend_query = service_level_trend_query.filter(or_(*extension_filters))
    if direction:
        service_level_trend_query = service_level_trend_query.filter(CDRRecord.direction == direction)
    
    service_level_daily = service_level_trend_query.group_by('date').order_by('date').all()
    
    service_level_trend = []
    for d in service_level_daily:
        within_threshold = d[1] or 0
        total_answered = d[2] or 0
        if total_answered > 0:
            percentage = (within_threshold / total_answered) * 100
        else:
            percentage = 0
        service_level_trend.append({'date': str(d[0]), 'value': percentage})
    
    # Get ASA trend (daily)
    asa_trend_query = db.query(
        func.date(local_start_timestamp).label('date'),
        func.avg(CDRRecord.cc_queue_answered_epoch - CDRRecord.cc_queue_joined_epoch).label('avg_asa'),
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None),
        CDRRecord.cc_queue_answered_epoch.isnot(None)
    )
    
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        asa_trend_query = asa_trend_query.filter(or_(*extension_filters))
    if direction:
        asa_trend_query = asa_trend_query.filter(CDRRecord.direction == direction)
    
    asa_daily = asa_trend_query.group_by('date').order_by('date').all()
    
    asa_trend = [{'date': str(d[0]), 'value': d[1] or 0} for d in asa_daily]
    
    # Get AHT trend (daily)
    aht_trend_query = db.query(
        func.date(local_start_timestamp).label('date'),
        func.avg(CDRRecord.billsec).label('avg_aht'),
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None),
        CDRRecord.cc_queue_answered_epoch.isnot(None)
    )
    
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        aht_trend_query = aht_trend_query.filter(or_(*extension_filters))
    if direction:
        aht_trend_query = aht_trend_query.filter(CDRRecord.direction == direction)
    
    aht_daily = aht_trend_query.group_by('date').order_by('date').all()
    
    aht_trend = [{'date': str(d[0]), 'value': d[1] or 0} for d in aht_daily]
    
    # Get busiest queues (top 3)
    busiest_queues_query = db.query(
        CDRRecord.cc_queue,
        func.count(func.distinct(
            func.concat(CDRRecord.caller_id_number, '|', cast(CDRRecord.cc_queue_joined_epoch, String))
        )).label('call_count')
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None)
    )
    
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        busiest_queues_query = busiest_queues_query.filter(or_(*extension_filters))
    if direction:
        busiest_queues_query = busiest_queues_query.filter(CDRRecord.direction == direction)
    
    busiest = busiest_queues_query.group_by(CDRRecord.cc_queue).order_by(desc('call_count')).limit(3).all()
    
    all_queues = db.query(Queue).all()
    queue_map_by_extension = {}
    for queue in all_queues:
        if not queue.queue_extension:
            continue
        queue_map_by_extension[queue.queue_extension] = queue
        if "@" in queue.queue_extension:
            queue_map_by_extension[queue.queue_extension.split("@", 1)[0]] = queue

    busiest_queues = []
    for cc_queue, call_count in busiest:
        queue = queue_map_by_extension.get(cc_queue)
        if not queue and cc_queue and '@' in cc_queue:
            queue = queue_map_by_extension.get(cc_queue.split('@', 1)[0])
        
        if queue:
            busiest_queues.append({
                'queueId': queue.queue_id,
                'queueName': queue.name,
                'callsHandled': call_count
            })
        else:
            busiest_queues.append({
                'queueId': None,
                'queueName': cc_queue,
                'callsHandled': call_count
            })
    
    # Get worst abandon queues (top 3 by abandon rate)
    # Use same methodology as overall calculation - group by (caller, join_time) first, then attribute to queue
    worst_abandon_results = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None)
    )
    
    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        worst_abandon_results = worst_abandon_results.filter(or_(*extension_filters))
    if direction:
        worst_abandon_results = worst_abandon_results.filter(CDRRecord.direction == direction)
    
    worst_abandon_results = worst_abandon_results.all()
    
    # First, group by (caller, join_time) to identify unique queue entries (same as overall calculation)
    unique_entries = {}
    for record in worst_abandon_results:
        key = (record.caller_id_number, record.cc_queue_joined_epoch)
        if key not in unique_entries:
            unique_entries[key] = []
        unique_entries[key].append(record)
    
    # Helper function to determine if a queue entry is truly abandoned (same as above)
    def is_true_abandoned_for_queue(records):
        # If any record was answered, not abandoned
        if any(r.cc_queue_answered_epoch is not None for r in records):
            return False
        
        # Check if any record matches abandoned criteria
        for record in records:
            # Must have billsec = 0
            if (record.billsec or 0) != 0:
                continue
            
            # Exclude deflects and blind transfers
            if (getattr(record, 'last_app', None) or '') == 'deflect':
                continue
            if (record.hangup_cause or '') == 'BLIND_TRANSFER':
                continue
            
            # Must show caller-abandoned behavior
            if (record.hangup_cause in ('ORIGINATOR_CANCEL', 'NO_ANSWER') or
                (getattr(record, 'cc_cause', None) or '') == 'TIMEOUT' or
                (getattr(record, 'call_disposition', None) or '') == 'missed'):
                return True
        
        return False
    
    # Now attribute each entry to a queue and track answered/abandoned status
    queue_stats = {}
    for entry_key, records in unique_entries.items():
        # Determine which queue this entry belongs to (use the first record's cc_queue)
        cc_queue = records[0].cc_queue
        
        if cc_queue not in queue_stats:
            queue_stats[cc_queue] = {'total': 0, 'answered': 0, 'abandoned': 0}
        
        queue_stats[cc_queue]['total'] += 1
        
        # Check if this entry was answered (any record has cc_queue_answered_epoch set)
        if any(r.cc_queue_answered_epoch is not None for r in records):
            queue_stats[cc_queue]['answered'] += 1
        elif is_true_abandoned_for_queue(records):
            queue_stats[cc_queue]['abandoned'] += 1
    
    # Calculate abandon rates per queue
    abandon_rates = []
    for cc_queue, stats in queue_stats.items():
        abandon_rate_for_queue = (stats['abandoned'] / stats['total'] * 100) if stats['total'] > 0 else 0
        abandon_rates.append((cc_queue, abandon_rate_for_queue, stats['abandoned'], stats['total']))
    
    # Sort by abandon rate descending and take top 3
    abandon_rates.sort(key=lambda x: x[1], reverse=True)
    
    worst_abandon_queues = []
    for cc_queue, queue_abandon_rate, abandoned, total_queued in abandon_rates[:3]:
        queue = queue_map_by_extension.get(cc_queue)
        if not queue and cc_queue and '@' in cc_queue:
            queue = queue_map_by_extension.get(cc_queue.split('@', 1)[0])
        
        if queue:
            worst_abandon_queues.append({
                'queueId': queue.queue_id,
                'queueName': queue.name,
                'abandonRate': queue_abandon_rate,
                'callsAbandoned': abandoned
            })
        else:
            worst_abandon_queues.append({
                'queueId': None,
                'queueName': cc_queue,
                'abandonRate': queue_abandon_rate,
                'callsAbandoned': abandoned
            })
    
    return {
        'offered': {
            'name': 'Total Offered',
            'value': total_offered_queue,
            'unit': 'calls',
            'definition': KPIDefinitions.VOLUME['total_queue_calls']['description'],
        },
        'answerRate': {
            'name': 'Answer Rate',
            'value': answer_rate,
            'unit': '%',
            'definition': KPIDefinitions.SERVICE_LEVEL['answer_rate']['description'],
        },
        'abandonRate': {
            'name': 'Abandon Rate',
            'value': abandon_rate,
            'unit': '%',
            'definition': KPIDefinitions.SERVICE_LEVEL['abandon_rate']['description'],
        },
        'serviceLevel': {
            'name': 'Service Level %',
            'value': service_level,
            'unit': '%',
            'definition': KPIDefinitions.SERVICE_LEVEL['service_level']['description'],
        },
        'asa': {
            'name': 'ASA',
            'value': avg_asa,
            'unit': 'seconds',
            'definition': KPIDefinitions.SERVICE_LEVEL['asa']['description'],
        },
        'aht': {
            'name': 'AHT',
            'value': avg_aht,
            'unit': 'seconds',
            'definition': KPIDefinitions.HANDLE_TIME['aht']['description'],
        },
        'avgMos': {
            'name': 'Avg MOS',
            'value': avg_mos,
            'unit': 'score',
            'definition': KPIDefinitions.QUALITY['avg_mos']['description'],
        },
        'totalTalkTime': {
            'name': 'Total Talk Time',
            'value': total_talk_time,
            'unit': 'seconds',
            'definition': KPIDefinitions.TALK_TIME['total_talk_time']['description'],
        },
        'trends': {
            'offered': offered_trend,
            'answered': answered_trend,
            'abandoned': [],  # TODO: implement
            'serviceLevel': service_level_trend,
            'asa': asa_trend,
            'aht': aht_trend,
            'mos': [],
            'callVolumeBuckets': {
                'byDayOfWeek': weekday_call_volume_buckets,
                'byHourOfDay': hour_call_volume_buckets,
            },
        },
        'rankings': {
            'busiestQueues': [
                {
                    'name': item.get('queueName'),
                    'calls': item.get('callsHandled')
                }
                for item in busiest_queues
            ],
            'worstAbandonQueues': [
                {
                    'name': item.get('queueName'),
                    'rate': item.get('abandonRate')
                }
                for item in worst_abandon_queues
            ],
            'worstAsaQueues': [],
            'lowestMosProviders': [],
        },
    }


@router.get("/queue-performance/{queue_id}")
async def get_queue_performance(
    queue_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get queue performance dashboard data"""
    # TODO: Implement queue performance endpoint
    return {
        'queueId': queue_id,
        'queueName': 'Queue Name',
        'metrics': {},
        'hourly': {},
        'breakdowns': {},
    }


@router.get("/agent-performance/{agent_uuid}")
async def get_agent_performance(
    agent_uuid: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get agent performance dashboard data"""
    # TODO: Implement agent performance endpoint
    return {
        'agentUuid': agent_uuid,
        'agentName': 'Agent Name',
        'leaderboardPosition': 0,
        'callsHandled': 0,
        'metrics': {},
    }


@router.get("/quality")
async def get_quality_metrics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get quality and telecom health metrics"""
    # TODO: Implement quality metrics endpoint
    return {}


@router.get("/queue-performance")
async def get_queue_performance(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_ids: Optional[List[str]] = Query(None),
    direction: Optional[str] = Query(None),
    timezone: str = Query("America/Phoenix"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get queue performance metrics with support for comparing 2-4 queues
    
    Includes:
    - KPI metrics per queue (offered, answered, abandoned, rates, ASA, AHT, service level, callbacks)
    - Heatmaps (offered by hour/day, abandon rate by hour/day, ASA by hour/day)
    - Breakdown charts (hangup causes, call outcomes)
    """
    
    # Default to last 7 days if not specified
    user_timezone = get_requested_timezone(timezone)
    if not end_date:
        end_date = datetime.now(user_timezone)
    if not start_date:
        start_date = end_date - timedelta(days=7)

    start_date = ensure_utc_datetime(start_date)
    end_date = ensure_utc_datetime(end_date)
    
    start_epoch = int(start_date.timestamp())
    end_epoch = int(end_date.timestamp())
    
    # Get queues to analyze
    if not queue_ids or len(queue_ids) == 0:
        # Get all queues if none specified
        queues = db.query(Queue).filter(Queue.enabled == True).all()
    else:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
    
    # Note: Frontend handles grouping and display of many queues efficiently
    results = []
    
    for queue in queues:
        queue_extension = queue.queue_extension
        
        # Base query for this queue
        base_query = db.query(CDRRecord).filter(
            CDRRecord.start_epoch >= start_epoch,
            CDRRecord.start_epoch <= end_epoch,
            CDRRecord.cc_queue.like(f"{queue_extension}@%"),
        )
        
        if direction:
            base_query = base_query.filter(CDRRecord.direction == direction)
        
        # Get all queue records for detailed analysis
        queue_records_query = db.query(CDRRecord).filter(
            CDRRecord.start_epoch >= start_epoch,
            CDRRecord.start_epoch <= end_epoch,
            CDRRecord.cc_queue_joined_epoch.isnot(None),
            CDRRecord.cc_queue.like(f"{queue_extension}@%"),
        )
        
        if direction:
            queue_records_query = queue_records_query.filter(CDRRecord.direction == direction)
        
        queue_records = queue_records_query.all()
        
        # Group by unique queue entries (caller + join time)
        unique_queue_entries = {}
        for record in queue_records:
            key = (record.caller_id_number, record.cc_queue_joined_epoch)
            if key not in unique_queue_entries:
                unique_queue_entries[key] = []
            unique_queue_entries[key].append(record)
        
        # Helper function to determine if a queue entry is truly abandoned
        def is_true_abandoned(records):
            if any(r.cc_queue_answered_epoch is not None for r in records):
                return False
            for record in records:
                if (record.billsec or 0) != 0:
                    continue
                if (getattr(record, 'last_app', None) or '') == 'deflect':
                    continue
                if (record.hangup_cause or '') == 'BLIND_TRANSFER':
                    continue
                if (record.hangup_cause in ('ORIGINATOR_CANCEL', 'NO_ANSWER') or
                    (getattr(record, 'cc_cause', None) or '') == 'TIMEOUT' or
                    (getattr(record, 'call_disposition', None) or '') == 'missed'):
                    return True
            return False
        
        # Count outcomes
        total_offered = len(unique_queue_entries)
        total_answered = sum(1 for records in unique_queue_entries.values() 
                            if any(r.cc_queue_answered_epoch is not None for r in records))
        total_abandoned = sum(1 for records in unique_queue_entries.values()
                             if is_true_abandoned(records))
        
        answer_rate = (total_answered / total_offered * 100) if total_offered > 0 else 0
        abandon_rate = (total_abandoned / total_offered * 100) if total_offered > 0 else 0
        
        # ASA calculations
        asa_records = [r for r in queue_records if r.cc_queue_answered_epoch and r.cc_queue_joined_epoch]
        asa_times = [r.cc_queue_answered_epoch - r.cc_queue_joined_epoch for r in asa_records]
        avg_asa = sum(asa_times) / len(asa_times) if asa_times else 0
        asa_p90 = sorted(asa_times)[int(len(asa_times) * 0.9)] if asa_times else 0
        
        # AHT calculations
        answered_records = [r for r in queue_records if r.cc_queue_answered_epoch]
        aht_times = [r.billsec + (r.hold_accum_seconds or 0) for r in answered_records]
        avg_aht = sum(aht_times) / len(aht_times) if aht_times else 0
        aht_p90 = sorted(aht_times)[int(len(aht_times) * 0.9)] if aht_times else 0
        
        # Service level (default 30s)
        service_level = 0
        if asa_records:
            threshold = 30
            within_threshold = sum(1 for time in asa_times if time <= threshold)
            service_level = (within_threshold / len(asa_records) * 100)
        
        # MOS calculations
        mos_records = [r for r in queue_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
        avg_mos = sum(r.rtp_audio_in_mos for r in mos_records) / len(mos_records) if mos_records else 0
        
        # Callbacks
        callback_records = [r for r in queue_records if r.cc_agent_type == 'callback']
        callbacks_offered = len(callback_records)
        callbacks_answered = len([r for r in callback_records if r.cc_queue_answered_epoch])
        
        # Repeat caller rate (simplified - calls from same number within time window)
        caller_numbers = [r.caller_id_number for r in queue_records if r.caller_id_number]
        unique_callers = len(set(caller_numbers))
        repeat_caller_rate = ((len(caller_numbers) - unique_callers) / len(caller_numbers) * 100) if caller_numbers else 0
        
        # Heatmap data - Offered by hour and day of week
        offered_heatmap = {}
        abandon_rate_heatmap = {}
        asa_heatmap = {}
        
        for record in queue_records:
            dt = datetime.fromtimestamp(record.start_epoch, user_timezone)
            hour = dt.hour
            day = dt.weekday()  # 0 = Monday, 6 = Sunday
            key = f"{day}_{hour}"
            
            if key not in offered_heatmap:
                offered_heatmap[key] = {"count": 0, "abandoned": 0, "asa_sum": 0, "asa_count": 0}
            
            offered_heatmap[key]["count"] += 1
            
            # Check if abandoned
            records_for_this = unique_queue_entries.get((record.caller_id_number, record.cc_queue_joined_epoch), [])
            if is_true_abandoned(records_for_this):
                offered_heatmap[key]["abandoned"] += 1
            
            # ASA
            if record.cc_queue_answered_epoch and record.cc_queue_joined_epoch:
                asa = record.cc_queue_answered_epoch - record.cc_queue_joined_epoch
                offered_heatmap[key]["asa_sum"] += asa
                offered_heatmap[key]["asa_count"] += 1
        
        # Convert heatmap to array format
        offered_by_hour_day = []
        abandon_rate_by_hour_day = []
        asa_by_hour_day = []
        
        for day in range(7):
            for hour in range(24):
                key = f"{day}_{hour}"
                data = offered_heatmap.get(key, {"count": 0, "abandoned": 0, "asa_sum": 0, "asa_count": 0})
                
                offered_by_hour_day.append({
                    "day": day,
                    "hour": hour,
                    "value": data["count"]
                })
                
                abandon_rate = (data["abandoned"] / data["count"] * 100) if data["count"] > 0 else 0
                abandon_rate_by_hour_day.append({
                    "day": day,
                    "hour": hour,
                    "value": round(abandon_rate, 2)
                })
                
                avg_asa_cell = (data["asa_sum"] / data["asa_count"]) if data["asa_count"] > 0 else 0
                asa_by_hour_day.append({
                    "day": day,
                    "hour": hour,
                    "value": round(avg_asa_cell, 2)
                })
        
        # Hangup causes breakdown
        hangup_causes = {}
        for record in queue_records:
            cause = record.hangup_cause or "UNKNOWN"
            hangup_causes[cause] = hangup_causes.get(cause, 0) + 1
        
        hangup_causes_list = [
            {"cause": cause, "count": count, "percentage": round(count / len(queue_records) * 100, 2)}
            for cause, count in sorted(hangup_causes.items(), key=lambda x: x[1], reverse=True)
        ] if queue_records else []
        
        # Call outcomes breakdown
        call_outcomes = {
            "answered": total_answered,
            "abandoned": total_abandoned,
            "other": total_offered - total_answered - total_abandoned
        }
        
        call_outcomes_list = [
            {"outcome": outcome, "count": count, "percentage": round(count / total_offered * 100, 2)}
            for outcome, count in call_outcomes.items()
        ] if total_offered > 0 else []
        
        # Hourly time series aggregation
        hourly_buckets = {}
        
        # Group records by hour bucket
        for record in queue_records:
            # Round timestamp down to the hour
            dt = datetime.fromtimestamp(record.start_epoch, user_timezone)
            hour_bucket = dt.replace(minute=0, second=0, microsecond=0)
            timestamp_key = hour_bucket.isoformat()
            
            if timestamp_key not in hourly_buckets:
                hourly_buckets[timestamp_key] = {
                    'records': [],
                    'unique_entries': {}
                }
            
            hourly_buckets[timestamp_key]['records'].append(record)
            
            # Also track unique entries per hour
            entry_key = (record.caller_id_number, record.cc_queue_joined_epoch)
            if entry_key not in hourly_buckets[timestamp_key]['unique_entries']:
                hourly_buckets[timestamp_key]['unique_entries'][entry_key] = []
            hourly_buckets[timestamp_key]['unique_entries'][entry_key].append(record)
        
        # Calculate metrics for each hour bucket
        hourly_data = []
        for timestamp_key in sorted(hourly_buckets.keys()):
            bucket = hourly_buckets[timestamp_key]
            bucket_records = bucket['records']
            bucket_entries = bucket['unique_entries']
            
            # Count offered (unique entries in this hour)
            offered_count = len(bucket_entries)
            
            # Count answered
            answered_count = sum(1 for records in bucket_entries.values() 
                               if any(r.cc_queue_answered_epoch is not None for r in records))
            
            # Count abandoned
            abandoned_count = sum(1 for records in bucket_entries.values()
                                if is_true_abandoned(records))
            
            # Service level
            hour_asa_records = [r for r in bucket_records if r.cc_queue_answered_epoch and r.cc_queue_joined_epoch]
            hour_asa_times = [r.cc_queue_answered_epoch - r.cc_queue_joined_epoch for r in hour_asa_records]
            
            hour_service_level = 0
            if hour_asa_times:
                within_30 = sum(1 for t in hour_asa_times if t <= 30)
                hour_service_level = (within_30 / len(hour_asa_times) * 100)
            
            # ASA
            hour_asa = sum(hour_asa_times) / len(hour_asa_times) if hour_asa_times else None
            
            # AHT
            hour_answered_records = [r for r in bucket_records if r.cc_queue_answered_epoch]
            hour_aht_times = [r.billsec + (r.hold_accum_seconds or 0) for r in hour_answered_records]
            hour_aht = sum(hour_aht_times) / len(hour_aht_times) if hour_aht_times else None
            
            # MOS
            hour_mos_records = [r for r in bucket_records if r.rtp_audio_in_mos and r.rtp_audio_in_mos > 0]
            hour_mos = sum(r.rtp_audio_in_mos for r in hour_mos_records) / len(hour_mos_records) if hour_mos_records else None
            
            hourly_data.append({
                "timestamp": timestamp_key,
                "offered": offered_count,
                "answered": answered_count,
                "abandoned": abandoned_count,
                "service_level": round(hour_service_level, 2),
                "asa": round(hour_asa, 2) if hour_asa is not None else None,
                "aht": round(hour_aht, 2) if hour_aht is not None else None,
                "mos": round(hour_mos, 2) if hour_mos is not None else None,
            })
        
        # Build result for this queue
        queue_result = {
            "queue_id": str(queue.queue_id),
            "queue_name": queue.name,
            "metrics": {
                "offered": {"value": total_offered, "unit": "calls"},
                "answered": {"value": total_answered, "unit": "calls"},
                "abandoned": {"value": total_abandoned, "unit": "calls"},
                "answer_rate": {"value": round(answer_rate, 2), "unit": "%"},
                "abandon_rate": {"value": round(abandon_rate, 2), "unit": "%"},
                "asa_avg": {"value": round(avg_asa, 2), "unit": "seconds"},
                "asa_p90": {"value": round(asa_p90, 2), "unit": "seconds"},
                "aht_avg": {"value": round(avg_aht, 2), "unit": "seconds"},
                "aht_p90": {"value": round(aht_p90, 2), "unit": "seconds"},
                "service_level": {"value": round(service_level, 2), "unit": "%"},
                "mos_avg": {"value": round(avg_mos, 2), "unit": ""},
                "callbacks_offered": {"value": callbacks_offered, "unit": "calls"},
                "callbacks_answered": {"value": callbacks_answered, "unit": "calls"},
                "repeat_caller_rate": {"value": round(repeat_caller_rate, 2), "unit": "%"},
            },
            "heatmaps": {
                "offered_by_hour_day": offered_by_hour_day,
                "abandon_rate_by_hour_day": abandon_rate_by_hour_day,
                "asa_by_hour_day": asa_by_hour_day,
            },
            "breakdowns": {
                "hangup_causes": hangup_causes_list[:10],  # Top 10
                "call_outcomes": call_outcomes_list,
            },
            "hourly": hourly_data
        }
        
        results.append(queue_result)
    
    return {"queues": results}


@router.get("/queue-performance-report")
async def get_queue_performance_report(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_ids: Optional[List[str]] = Query(None),
    direction: Optional[str] = Query(None),
    exclude_deflects: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get queue performance report aligned with dashboard queue KPIs.

    This endpoint returns aggregated per-queue metrics using the same
    unique queue entry methodology as the queue performance dashboard.

    Key features:
    - Deduplication: Each unique queue entry is counted once
    - Service Level 30: Percentage of answered calls handled within 30 seconds
    - ASA: Average Speed of Answer per queue
    - AHT: Average Handle Time (talk time for answered records)
    """
    
    # Default to last 7 days if not specified
    if not end_date:
        end_date = datetime.now(dt_timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=7)
    
    start_epoch = int(start_date.timestamp())
    # Set end_epoch to end of day (23:59:59) to include full last day
    end_epoch = int((end_date.replace(hour=23, minute=59, second=59)).timestamp())
    
    print(f"=== Queue Performance Report ===")
    print(f"Start epoch: {start_epoch}, End epoch: {end_epoch}")
    print(f"Queue IDs filter: {queue_ids}")
    print(f"Exclude deflects: {exclude_deflects}")
    
    # Convert queue UUIDs to cc_queue identifiers (extension@context format)
    queue_extensions = None
    if queue_ids:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
        queue_extensions = [q.queue_extension for q in queues if q.queue_extension]
        print(f"Converted to queue extensions: {queue_extensions}")
    else:
        queues = db.query(Queue).all()

    queue_by_extension = {
        q.queue_extension: q
        for q in queues
        if q.queue_extension
    }
    
    # ======================================================================
    # STEP 1: Fetch all CDR records in the date range with queue data
    # ======================================================================
    base_query = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None),
    )

    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        base_query = base_query.filter(or_(*extension_filters))

    if direction:
        base_query = base_query.filter(CDRRecord.direction == direction)

    queue_records = base_query.all()
    print(f"Total CDR records with queue joins: {len(queue_records)}")

    # ======================================================================
    # STEP 2: Group by queue entry (caller + join time) per queue extension
    # ======================================================================
    queue_entries = {}
    queue_records_by_extension = {}

    for record in queue_records:
        cc_queue = record.cc_queue or ""
        extension = cc_queue.split("@", 1)[0] if "@" in cc_queue else cc_queue
        if not extension:
            continue

        entry_key = (record.caller_id_number, record.cc_queue_joined_epoch)

        if extension not in queue_entries:
            queue_entries[extension] = {}
            queue_records_by_extension[extension] = []

        if entry_key not in queue_entries[extension]:
            queue_entries[extension][entry_key] = []
        queue_entries[extension][entry_key].append(record)
        queue_records_by_extension[extension].append(record)

    # ======================================================================
    # STEP 3: Calculate metrics per queue extension
    # ======================================================================

    def is_true_abandoned(records):
        if any(r.cc_queue_answered_epoch is not None for r in records):
            return False

        for record in records:
            if (record.billsec or 0) != 0:
                continue
            if exclude_deflects and (getattr(record, 'last_app', None) or '') == 'deflect':
                continue
            if (record.hangup_cause or '') == 'BLIND_TRANSFER':
                continue
            if (record.hangup_cause in ('ORIGINATOR_CANCEL', 'NO_ANSWER') or
                (getattr(record, 'cc_cause', None) or '') == 'TIMEOUT' or
                (getattr(record, 'call_disposition', None) or '') == 'missed'):
                return True

        return False

    results = []

    for extension, entry_map in sorted(queue_entries.items()):
        # Count outcomes using unique queue entries
        offered = len(entry_map)
        answered = sum(1 for records in entry_map.values()
                       if any(r.cc_queue_answered_epoch is not None for r in records))
        abandoned = sum(1 for records in entry_map.values() if is_true_abandoned(records))

        # ASA and service level calculations use answered records for the queue
        queue_records_for_extension = queue_records_by_extension.get(extension, [])
        asa_records = [
            r for r in queue_records_for_extension
            if r.cc_queue_answered_epoch and r.cc_queue_joined_epoch
        ]
        asa_times = [r.cc_queue_answered_epoch - r.cc_queue_joined_epoch for r in asa_records]
        service_level_count = sum(1 for t in asa_times if t <= 30)
        service_level_30 = (service_level_count / len(asa_times) * 100) if asa_times else 0
        asa_sec = sum(asa_times) / len(asa_times) if asa_times else 0

        # AHT calculations use answered records for the queue
        answered_records = [r for r in queue_records_for_extension if r.cc_queue_answered_epoch]
        aht_times = [r.billsec + (r.hold_accum_seconds or 0) for r in answered_records]
        aht_sec = sum(aht_times) / len(aht_times) if aht_times else 0

        queue_obj = queue_by_extension.get(extension)
        queue_id_value = queue_obj.queue_id if queue_obj else extension
        queue_name = queue_obj.name if queue_obj else extension

        result = {
            'queue_id': queue_id_value,
            'queue_name': queue_name,
            'offered': offered,
            'answered': answered,
            'abandoned': abandoned,
            'service_level_30': round(service_level_30, 2),
            'asa_sec': round(asa_sec, 2),
            'aht_sec': round(aht_sec, 2),
            # Additional fields for frontend total calculations
            'sl30_numerator': service_level_count,
            'sl30_denominator': len(asa_times),
            'asa_answered_count': len(asa_times),
            'aht_answered_count': len(aht_times),
        }

        results.append(result)
    
    # Sort by offered descending (default sort)
    results.sort(key=lambda x: x['offered'], reverse=True)
    
    return {
        'start': start_date.isoformat(),
        'end': end_date.isoformat(),
        'rows': results,
    }


@router.get("/repeat-callers", response_model=RepeatCallersResponse)
async def get_repeat_callers(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_ids: Optional[List[str]] = Query(None),
    direction: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get repeat caller metrics"""
    if not end_date:
        end_date = datetime.now(dt_timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=7)

    start_epoch = int(start_date.timestamp())
    end_epoch = int((end_date.replace(hour=23, minute=59, second=59)).timestamp())

    queue_extensions = None
    if queue_ids:
        queues = db.query(Queue).filter(Queue.queue_id.in_(queue_ids)).all()
        queue_extensions = [q.queue_extension for q in queues if q.queue_extension]

    effective_direction = direction or "inbound"

    query = db.query(
        CDRRecord.caller_id_number,
        CDRRecord.cc_queue_joined_epoch,
        CDRRecord.cc_queue,
        CDRRecord.cc_queue_answered_epoch,
    ).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.cc_queue_joined_epoch.isnot(None),
    )

    if queue_extensions:
        extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
        query = query.filter(or_(*extension_filters))

    if effective_direction:
        query = query.filter(CDRRecord.direction == effective_direction)

    records = query.all()

    # Build queue name map
    queue_name_by_extension = {}
    for queue in db.query(Queue).all():
        queue_extension = queue.queue_extension
        if not queue_extension:
            continue
        queue_name = getattr(queue, "name", None) or getattr(queue, "queue_name", None) or queue_extension
        queue_name_by_extension[queue_extension] = queue_name
        if "@" in queue_extension:
            queue_name_by_extension[queue_extension.split("@")[0]] = queue_name

    def resolve_queue_name(cc_queue: Optional[str]) -> Optional[str]:
        if not cc_queue:
            return None
        queue_key = cc_queue.split("@")[0] if "@" in cc_queue else cc_queue
        return queue_name_by_extension.get(queue_key, cc_queue)

    def mask_number(number: str) -> str:
        digits = "".join([c for c in number if c.isdigit()])
        if not digits:
            return number
        if len(digits) <= 4:
            return "*" * len(digits)
        return ("*" * (len(digits) - 4)) + digits[-4:]

    user_can_view = False
    user_id = current_user.get("user_id")
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_can_view = bool(user.can_view_unmasked_numbers) or user.role in ("super_admin", "admin", "operator")

    caller_entries = {}
    caller_queues = {}
    entry_answered = {}

    for caller_id_number, cc_queue_joined_epoch, cc_queue, cc_queue_answered_epoch in records:
        if not caller_id_number or not cc_queue_joined_epoch:
            continue

        entry_key = (caller_id_number, cc_queue_joined_epoch)
        if caller_id_number not in caller_entries:
            caller_entries[caller_id_number] = set()
        caller_entries[caller_id_number].add(entry_key)

        if entry_key not in entry_answered:
            entry_answered[entry_key] = False
        if cc_queue_answered_epoch is not None:
            entry_answered[entry_key] = True

        queue_name = resolve_queue_name(cc_queue)
        if queue_name:
            if caller_id_number not in caller_queues:
                caller_queues[caller_id_number] = set()
            caller_queues[caller_id_number].add(queue_name)

    repeat_callers = []
    for caller_id_number, entries in caller_entries.items():
        call_count = len(entries)
        if call_count <= 1:
            continue
        answered_count = sum(1 for entry in entries if entry_answered.get(entry, False))
        abandoned_count = call_count - answered_count
        queues = sorted(caller_queues.get(caller_id_number, []))
        display_number = caller_id_number if user_can_view else mask_number(caller_id_number)
        repeat_callers.append({
            "caller_id_number": display_number,
            "call_count": call_count,
            "answered_count": answered_count,
            "abandoned_count": abandoned_count,
            "queues": queues,
        })

    repeat_callers.sort(
        key=lambda row: (-row["call_count"], row["caller_id_number"])
    )

    return {
        "start": start_date,
        "end": end_date,
        "repeat_callers": repeat_callers,
    }


@router.get("/outbound-calls")
async def get_outbound_calls(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_ids: Optional[List[str]] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get outbound calls statistics
    
    Returns:
    - by_user: List of outbound stats by agent
    - by_prefix: List of outbound stats grouped by first 3 letters of agent name
    """
    
    # Default to last 7 days if not specified
    if not end_date:
        end_date = datetime.now(dt_timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=7)
    
    start_epoch = int(start_date.timestamp())
    end_epoch = int((end_date.replace(hour=23, minute=59, second=59)).timestamp())
    
    # Filter outbound calls only
    base_query = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch,
        CDRRecord.start_epoch <= end_epoch,
        CDRRecord.direction == "outbound",
    )
    
    # Convert queue UUIDs to cc_queue identifiers if provided
    if queue_ids:
        queue_extensions = []
        for queue_id in queue_ids:
            queue = db.query(Queue).filter(Queue.queue_id == queue_id).first()
            if queue and queue.queue_extension:
                queue_extensions.append(queue.queue_extension)
        
        if queue_extensions:
            extension_filters = [CDRRecord.cc_queue.like(f"{ext}@%") for ext in queue_extensions]
            base_query = base_query.filter(or_(*extension_filters))
    
    # Build extension mappings used for user attribution.
    extensions = db.query(Extension).all()
    extension_uuid_map = {
        str(ext.extension_uuid): ext.user_name
        for ext in extensions
        if ext.extension_uuid and ext.user_name
    }
    extension_number_map = {
        str(ext.extension): ext.user_name
        for ext in extensions
        if ext.extension and ext.user_name
    }
    known_user_name_map = {
        str(ext.user_name).strip().lower(): ext.user_name
        for ext in extensions
        if ext.user_name
    }
    # Word-set map for fuzzy person-name matching.
    # Splits each user_name into lowercase words so that a caller_id_name like
    # "Annette Zaballero" can match "WIF-CS-Annette Zaballero" by word overlap.
    user_name_word_map = []
    for ext in extensions:
        if ext.user_name:
            words = set(re.split(r'[\s\-_]+', ext.user_name.lower()))
            words.discard('')
            if len(words) >= 2:
                user_name_word_map.append((words, ext.user_name))

    # Build agent-name and extension alias maps for outbound caller attribution.
    known_agent_name_map = {}
    agent_name_word_map = []
    agent_extension_map = {}
    
    # Build agent identifier map for resolving canonical agent names
    agent_map = {}
    for agent in db.query(Agent).all():
        if not agent.agent_name:
            continue
        normalized_agent_name = agent.agent_name.strip().lower()
        if normalized_agent_name:
            known_agent_name_map[normalized_agent_name] = agent.agent_name

        name_words = set(re.split(r'[\s\-_]+', normalized_agent_name))
        name_words.discard('')
        if len(name_words) >= 2:
            agent_name_word_map.append((name_words, agent.agent_name))

        if agent.agent_uuid:
            agent_map[agent.agent_uuid] = agent.agent_name
        if agent.extension:
            ext_str = str(agent.extension).strip()
            agent_map[ext_str] = agent.agent_name
            agent_extension_map[ext_str] = agent.agent_name
        if agent.agent_contact:
            agent_map[agent.agent_contact] = agent.agent_name
            contact_match = re.search(r'user/(\d{3,6})@', str(agent.agent_contact))
            if contact_match:
                agent_extension_map[contact_match.group(1)] = agent.agent_name
        agent_map[agent.agent_name] = agent.agent_name

    # Group by extension to collect per-user stats
    user_stats = {}  # user_name/extension_uuid -> {count, talk_time_sec}
    prefix_stats = {}  # first_3_letters -> {count, talk_time_sec}
    diagnostics = {
        "total_records": 0,
        "attributed_records": 0,
        "unknown_records": 0,
        "unknown_rate_pct": 0,
        "attribution_sources": {
            "agent_map": 0,
            "extension_uuid": 0,
            "caller_name_exact": 0,
            "caller_name_extension": 0,
            "caller_name_fuzzy": 0,
            "caller_number_extension": 0,
            "raw_identifier_fallback": 0,
        },
        "unknown_reasons": {
            "missing_all_identifiers": 0,
            "extension_uuid_unmapped": 0,
            "unresolved_with_identifiers": 0,
        },
        "top_unknown_caller_labels": [],
    }
    unknown_label_counts = {}

    for record in base_query.all():
        diagnostics["total_records"] += 1

        # Resolve canonical agent name, preferring call-center agent identifiers.
        user_name = None
        source = None
        has_cc_agent_uuid = bool(record.cc_agent_uuid)
        has_cc_agent = bool(record.cc_agent)
        has_extension_uuid = bool(record.extension_uuid)
        has_any_identifier = has_cc_agent_uuid or has_cc_agent or has_extension_uuid
        extension_uuid_matched = False

        if record.cc_agent_uuid:
            user_name = agent_map.get(record.cc_agent_uuid)
            if user_name:
                source = "agent_map"

        if not user_name and record.cc_agent:
            user_name = agent_map.get(record.cc_agent)
            if user_name:
                source = "agent_map"

        if record.extension_uuid:
            user_name = user_name or extension_uuid_map.get(str(record.extension_uuid))
            if user_name and source is None:
                source = "extension_uuid"
                extension_uuid_matched = True

        # Fallback for outbound calls that do not populate call-center fields:
        # map caller_id_name via known names or embedded extension numbers.
        if not user_name and record.caller_id_name:
            caller_label = str(record.caller_id_name).strip()
            if caller_label:
                label_key = caller_label.lower()
                user_name = known_agent_name_map.get(label_key) or known_user_name_map.get(label_key)
                if user_name:
                    source = "caller_name_exact"

            if not user_name:
                for token in re.findall(r"\b\d{3,6}\b", caller_label):
                    mapped_name = agent_extension_map.get(token) or extension_number_map.get(token)
                    if mapped_name:
                        user_name = mapped_name
                        source = "caller_name_extension"
                        break

        if not user_name and record.cc_agent_uuid:
            user_name = record.cc_agent_uuid
            source = "raw_identifier_fallback"

        if not user_name and record.cc_agent:
            user_name = record.cc_agent
            source = "raw_identifier_fallback"

        # For outbound calls, caller_id_number is the dialing extension — try it directly.
        if not user_name and record.caller_id_number:
            number_key = str(record.caller_id_number).strip()
            user_name = agent_extension_map.get(number_key) or extension_number_map.get(number_key)
            if user_name:
                source = "caller_number_extension"

        # Fuzzy word-match: "Annette Zaballero" → "WIF-CS-Annette Zaballero"
        if not user_name and record.caller_id_name:
            caller_words = set(re.split(r'[\s\-_]+', record.caller_id_name.strip().lower()))
            caller_words.discard('')
            if len(caller_words) >= 2:
                for agent_words, agent_user_name in agent_name_word_map:
                    if caller_words.issubset(agent_words) or agent_words.issuperset(caller_words):
                        user_name = agent_user_name
                        source = "caller_name_fuzzy"
                        break

            if not user_name and len(caller_words) >= 2:
                for ext_words, ext_user_name in user_name_word_map:
                    if caller_words.issubset(ext_words) or ext_words.issuperset(caller_words):
                        user_name = ext_user_name
                        source = "caller_name_fuzzy"
                        break

        if not user_name:
            # Could not resolve to a known agent/extension — trunk/company call.
            user_name = "unknown"

            diagnostics["unknown_records"] += 1
            if not has_any_identifier:
                diagnostics["unknown_reasons"]["missing_all_identifiers"] += 1
            elif has_extension_uuid and not extension_uuid_matched:
                diagnostics["unknown_reasons"]["extension_uuid_unmapped"] += 1
            else:
                diagnostics["unknown_reasons"]["unresolved_with_identifiers"] += 1

            unknown_label = (record.caller_id_name or "(blank)").strip() or "(blank)"
            unknown_label_counts[unknown_label] = unknown_label_counts.get(unknown_label, 0) + 1
        else:
            diagnostics["attributed_records"] += 1
            if source:
                diagnostics["attribution_sources"].setdefault(source, 0)
                diagnostics["attribution_sources"][source] += 1

        normalized_name = (user_name or "").strip()
        if normalized_name.lower() in {"", "unknown", "none", "null", "n/a", "unassigned"}:
            user_name = "Unknown"
        else:
            user_name = normalized_name

        # Determine talk time via billsec
        talk_time = (record.billsec or 0)

        # Per-user stats
        if user_name not in user_stats:
            user_stats[user_name] = {"count": 0, "total_talk_time": 0}
        user_stats[user_name]["count"] += 1
        user_stats[user_name]["total_talk_time"] += talk_time

        # Per-prefix stats (first 3 letters)
        prefix = user_name[:3] if len(user_name) >= 3 else user_name
        if prefix not in prefix_stats:
            prefix_stats[prefix] = {"count": 0, "total_talk_time": 0}
        prefix_stats[prefix]["count"] += 1
        prefix_stats[prefix]["total_talk_time"] += talk_time

    # Format by_user results
    by_user = []
    for user_name, stats in user_stats.items():
        aht = stats["total_talk_time"] / stats["count"] if stats["count"] > 0 else 0
        by_user.append({
            "agent_name": user_name,
            "count": stats["count"],
            "aht_seconds": aht,
        })

    # Sort by count descending, but keep Unknown at the bottom.
    by_user.sort(
        key=lambda x: (
            (x["agent_name"] or "").strip().lower() in {"unknown", "", "none", "null", "n/a", "unassigned"},
            -x["count"],
            x["agent_name"],
        )
    )

    try:
        # Format by_prefix results
        by_prefix = []
        for prefix, stats in prefix_stats.items():
            aht = stats["total_talk_time"] / stats["count"] if stats["count"] > 0 else 0
            by_prefix.append({
                "prefix": prefix,
                "count": stats["count"],
                "aht_seconds": aht,
            })

        # Sort by count descending, but keep unknown prefixes at the bottom.
        by_prefix.sort(
            key=lambda x: (
                (x["prefix"] or "").strip().lower() in {"unk", "unknown", "", "n/a"},
                -x["count"],
                x["prefix"],
            )
        )

        if diagnostics["total_records"] > 0:
            diagnostics["unknown_rate_pct"] = round(
                (diagnostics["unknown_records"] / diagnostics["total_records"]) * 100,
                2,
            )

        diagnostics["top_unknown_caller_labels"] = [
            {"label": label, "count": count}
            for label, count in sorted(unknown_label_counts.items(), key=lambda item: item[1], reverse=True)[:10]
        ]

        return {
            "start": start_date,
            "end": end_date,
            "by_user": by_user,
            "by_prefix": by_prefix,
            "diagnostics": diagnostics,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Outbound calls processing error: {e}")
