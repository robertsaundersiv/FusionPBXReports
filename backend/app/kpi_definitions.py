"""
KPI Definitions Module - Single Source of Truth for all metrics
This module ensures consistent KPI calculation across ETL and API
"""
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class CallStatus(str, Enum):
    """Call status classification"""
    ANSWERED = "answered"
    ABANDONED = "abandoned"
    OFFERED = "offered"
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    CALLBACK = "callback"


@dataclass
class KPIDefinition:
    """Definition of a single KPI"""
    name: str
    description: str
    calculation: str
    unit: str
    excludes: List[str]
    threshold: Dict = None


class KPIDefinitions:
    """Centralized KPI definitions for the system"""

    # Call Classification Rules
    CALL_CLASSIFICATIONS = {
        "answered": {
            "description": "Call status is answered OR billsec > 0",
            "definition": "status == 'answered' OR billsec > 0",
        },
        "offered_queue": {
            "description": "Queue calls (cc_queue_joined_epoch IS NOT NULL)",
            "definition": "cc_queue_joined_epoch IS NOT NULL",
        },
        "inbound_offered": {
            "description": "All inbound calls (direction == 'inbound')",
            "definition": "direction == 'inbound'",
        },
        "abandoned": {
            "description": "Queue call not answered (cc_queue_joined_epoch IS NOT NULL AND cc_queue_answered_epoch IS NULL)",
            "definition": "cc_queue_joined_epoch IS NOT NULL AND cc_queue_answered_epoch IS NULL",
        },
        "callback": {
            "description": "Callback call type (cc_agent_type == 'callback')",
            "definition": "cc_agent_type == 'callback'",
        },
    }

    # Volume KPIs
    VOLUME = {
        "total_inbound_calls": {
            "name": "Total Inbound Calls",
            "description": "Total inbound calls offered to the system",
            "calculation": "COUNT(*) WHERE direction='inbound'",
            "unit": "calls",
            "excludes": ["internal", "test_calls"],
        },
        "total_queue_calls": {
            "name": "Total Queue-Offered Calls",
            "description": "Total calls offered to queues",
            "calculation": "COUNT(*) WHERE cc_queue_joined_epoch IS NOT NULL",
            "unit": "calls",
            "excludes": [],
        },
        "answered_calls": {
            "name": "Answered Calls",
            "description": "Calls answered by agents or system",
            "calculation": "COUNT(*) WHERE status='answered' OR billsec > 0",
            "unit": "calls",
            "excludes": [],
        },
        "abandoned_calls": {
            "name": "Abandoned Calls",
            "description": "Queue calls not answered",
            "calculation": "COUNT(*) WHERE cc_queue_joined_epoch IS NOT NULL AND cc_queue_answered_epoch IS NULL",
            "unit": "calls",
            "excludes": [],
        },
    }

    # Service Level KPIs
    SERVICE_LEVEL = {
        "answer_rate": {
            "name": "Answer Rate",
            "description": "Percentage of offered calls that were answered",
            "calculation": "(answered_calls / offered_calls) * 100",
            "unit": "%",
            "excludes": [],
            "thresholds": {"good": 80, "warning": 70},
        },
        "abandon_rate": {
            "name": "Abandon Rate",
            "description": "Percentage of queue calls that were abandoned",
            "calculation": "(abandoned_calls / queue_offered_calls) * 100",
            "unit": "%",
            "excludes": [],
            "thresholds": {"good": 10, "warning": 20},
        },
        "asa": {
            "name": "Average Speed of Answer (ASA)",
            "description": "Average time from queue join to answer for answered queue calls",
            "calculation": "AVG(cc_queue_answered_epoch - cc_queue_joined_epoch) WHERE cc_queue_answered_epoch IS NOT NULL",
            "unit": "seconds",
            "excludes": [],
            "thresholds": {"good": 30, "warning": 60},
        },
        "wait_time_avg": {
            "name": "Average Wait Time",
            "description": "Average time customer waited in queue",
            "calculation": "AVG(cc_queue_answered_epoch - cc_queue_joined_epoch) WHERE status='answered'",
            "unit": "seconds",
            "excludes": [],
        },
        "wait_time_p50": {
            "name": "Wait Time P50 (Median)",
            "description": "Median wait time in queue",
            "calculation": "PERCENTILE(cc_queue_answered_epoch - cc_queue_joined_epoch, 50)",
            "unit": "seconds",
            "excludes": [],
        },
        "wait_time_p90": {
            "name": "Wait Time P90",
            "description": "90th percentile wait time in queue",
            "calculation": "PERCENTILE(cc_queue_answered_epoch - cc_queue_joined_epoch, 90)",
            "unit": "seconds",
            "excludes": [],
        },
        "service_level": {
            "name": "Service Level %",
            "description": "Percentage of answered queue calls within threshold seconds",
            "calculation": "(COUNT(*) WHERE (cc_queue_answered_epoch - cc_queue_joined_epoch) <= threshold / answered_queue_calls) * 100",
            "unit": "%",
            "excludes": [],
            "default_threshold": 30,
            "thresholds": {"good": 80, "warning": 70},
        },
    }

    # Handle Time KPIs
    HANDLE_TIME = {
        "aht": {
            "name": "Average Handle Time",
            "description": "Average total call duration including talk time and hold time",
            "calculation": "AVG(billsec + hold_accum_seconds) WHERE status='answered'",
            "unit": "seconds",
            "excludes": [],
            "thresholds": {"good": 300, "warning": 600},
        },
        "aht_p90": {
            "name": "AHT P90",
            "description": "90th percentile handle time",
            "calculation": "PERCENTILE(billsec + hold_accum_seconds, 90) WHERE status='answered'",
            "unit": "seconds",
            "excludes": [],
        },
    }

    # Quality KPIs
    QUALITY = {
        "avg_mos": {
            "name": "Average MOS (Mean Opinion Score)",
            "description": "Average voice quality rating",
            "calculation": "AVG(rtp_audio_in_mos) WHERE status='answered'",
            "unit": "score",
            "excludes": ["no_media"],
            "thresholds": {"good": 4.0, "warning": 3.8},
        },
        "mos_p10": {
            "name": "MOS P10",
            "description": "10th percentile MOS score (worst 10% of calls)",
            "calculation": "PERCENTILE(rtp_audio_in_mos, 10) WHERE status='answered'",
            "unit": "score",
            "excludes": [],
        },
        "bad_call_rate": {
            "name": "Bad Call Rate",
            "description": "Percentage of calls with MOS below threshold",
            "calculation": "(COUNT(*) WHERE rtp_audio_in_mos < threshold / answered_calls) * 100",
            "unit": "%",
            "excludes": ["no_media"],
            "default_threshold": 3.8,
            "thresholds": {"good": 5, "warning": 10},
        },
        "codec_distribution": {
            "name": "Codec Distribution",
            "description": "Percentage of calls by read/write codec pairs",
            "calculation": "GROUP BY read_codec, write_codec; COUNT(*) / total_calls * 100",
            "unit": "%",
            "excludes": [],
        },
        "pdd_avg": {
            "name": "Post Dial Delay (PDD) Average",
            "description": "Average time from dial to first ringing",
            "calculation": "AVG(pdd_ms)",
            "unit": "milliseconds",
            "excludes": [],
            "thresholds": {"good": 200, "warning": 500},
        },
    }

    # Failure KPIs
    FAILURES = {
        "hangup_cause_distribution": {
            "name": "Hangup Cause Distribution",
            "description": "Count and percentage breakdown by hangup cause",
            "calculation": "GROUP BY hangup_cause; COUNT(*) / total_calls * 100",
            "unit": "%",
            "excludes": [],
        },
        "q850_distribution": {
            "name": "Q.850 Code Distribution",
            "description": "ISDN cause code breakdown",
            "calculation": "GROUP BY q850_cause; COUNT(*) / total_calls * 100",
            "unit": "%",
            "excludes": [],
        },
        "sip_disposition_distribution": {
            "name": "SIP Disposition Distribution",
            "description": "SIP hangup disposition breakdown",
            "calculation": "GROUP BY sip_hangup_disposition; COUNT(*) / total_calls * 100",
            "unit": "%",
            "excludes": [],
        },
        "failure_rate": {
            "name": "Failure Rate",
            "description": "Percentage of calls not answered or with failure causes",
            "calculation": "(non_answered_calls / total_calls) * 100",
            "unit": "%",
            "excludes": [],
        },
    }

    # Callback KPIs
    CALLBACKS = {
        "callbacks_offered": {
            "name": "Callbacks Offered",
            "description": "Total callback requests generated",
            "calculation": "COUNT(*) WHERE cc_agent_type='callback'",
            "unit": "calls",
            "excludes": [],
        },
        "callbacks_answered": {
            "name": "Callbacks Answered",
            "description": "Callback requests completed",
            "calculation": "COUNT(*) WHERE cc_agent_type='callback' AND status='answered'",
            "unit": "calls",
            "excludes": [],
        },
        "callback_completion_rate": {
            "name": "Callback Completion Rate",
            "description": "Percentage of callbacks that were completed",
            "calculation": "(callbacks_answered / callbacks_offered) * 100",
            "unit": "%",
            "excludes": [],
            "thresholds": {"good": 90, "warning": 75},
        },
    }

    # Repeat Caller KPIs
    REPEAT_CALLERS = {
        "repeat_caller_rate": {
            "name": "Repeat Caller Rate",
            "description": "Percentage of inbound calls from repeat callers (>1 call in N hours, default 24)",
            "calculation": "(COUNT(DISTINCT caller_id_number WHERE call_count > 1) / total_inbound_calls) * 100",
            "unit": "%",
            "excludes": ["blocked_numbers"],
            "default_window": 24,
        },
        "repeat_after_abandon_rate": {
            "name": "Repeat After Abandon Rate",
            "description": "Percentage of abandoned calls where same caller called back within N hours",
            "calculation": "(COUNT(caller_id_number WHERE previously_abandoned_within_N_hours) / abandoned_calls) * 100",
            "unit": "%",
            "excludes": [],
            "default_window": 24,
        },
    }

    # Talk Time KPIs
    TALK_TIME = {
        "total_talk_time": {
            "name": "Total Talk Time",
            "description": "Sum of all billable seconds for all calls",
            "calculation": "SUM(billsec)",
            "unit": "seconds",
            "excludes": [],
        },
        "total_hold_time": {
            "name": "Total Hold Time",
            "description": "Sum of all hold time across all calls",
            "calculation": "SUM(hold_accum_seconds)",
            "unit": "seconds",
            "excludes": [],
        },
    }

    @staticmethod
    def get_all_definitions() -> Dict:
        """Return all KPI definitions"""
        return {
            "classifications": KPIDefinitions.CALL_CLASSIFICATIONS,
            "volume": KPIDefinitions.VOLUME,
            "service_level": KPIDefinitions.SERVICE_LEVEL,
            "handle_time": KPIDefinitions.HANDLE_TIME,
            "quality": KPIDefinitions.QUALITY,
            "failures": KPIDefinitions.FAILURES,
            "callbacks": KPIDefinitions.CALLBACKS,
            "repeat_callers": KPIDefinitions.REPEAT_CALLERS,
            "talk_time": KPIDefinitions.TALK_TIME,
        }

    @staticmethod
    def get_kpi_definition(category: str, kpi_name: str) -> Dict:
        """Get a specific KPI definition"""
        definitions = KPIDefinitions.get_all_definitions()
        category_defs = definitions.get(category, {})
        return category_defs.get(kpi_name, {})
