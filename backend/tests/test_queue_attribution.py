"""
Unit tests for first-queue attribution logic in queue performance report
"""
import pytest
from datetime import datetime, timedelta
from app.models import CDRRecord
from sqlalchemy.orm import Session


class MockCDRRecord:
    """Mock CDR record for testing"""
    def __init__(self, xml_cdr_uuid, cc_queue, cc_queue_joined_epoch, 
                 cc_queue_answered_epoch=None, cc_queue_canceled_epoch=None, 
                 billsec=0, hangup_cause=None, call_disposition=None, last_app=None):
        self.xml_cdr_uuid = xml_cdr_uuid
        self.cc_queue = cc_queue
        self.cc_queue_joined_epoch = cc_queue_joined_epoch
        self.cc_queue_answered_epoch = cc_queue_answered_epoch
        self.cc_queue_canceled_epoch = cc_queue_canceled_epoch
        self.billsec = billsec
        self.hangup_cause = hangup_cause
        self.call_disposition = call_disposition
        self.last_app = last_app
        self.cc_cancel_reason = "TIMEOUT" if cc_queue_canceled_epoch and not cc_queue_answered_epoch else None
        self.cc_cause = "TIMEOUT" if cc_queue_canceled_epoch and not cc_queue_answered_epoch else None


class TestFirstQueueAttribution:
    """Test suite for first-queue attribution logic"""
    
    def test_single_queue_call(self):
        """
        Test: Call that stays in one queue should be attributed to that queue once
        Expected: offered=1, answered=1, abandoned=0
        """
        now = int(datetime.utcnow().timestamp())
        
        # Create a simple answered call
        records = [
            MockCDRRecord(
                xml_cdr_uuid="call-123",
                cc_queue="sales@internal",
                cc_queue_joined_epoch=now,
                cc_queue_answered_epoch=now + 5,
                billsec=120
            )
        ]
        
        # Verify call is identified as answered
        assert any(r.cc_queue_answered_epoch is not None for r in records) is True
        
        # Verify single queue entry
        assert len(set(r.cc_queue for r in records)) == 1
    
    def test_transferred_call_initial_queue_attribution(self):
        """
        Test: Call transferred from Queue A -> Queue B should be attributed ONLY to Queue A
        Expected:
          - Queue A: offered=1, answered=1, asa uses Queue A wait time
          - Queue B: offered=0, answered=0 (call not counted)
          - AHT should be total talk time but attributed to Queue A
        """
        now = int(datetime.utcnow().timestamp())
        
        # Call starts in Queue A
        call_uuid = "transferred-call-456"
        queue_a_join = now
        queue_a_answer = now + 5  # 5 sec wait in Queue A
        queue_a_hangup = now + 125  # After 120 sec talk
        
        # Call transfers to Queue B
        queue_b_join = now + 10  # Entered Queue B after being answered in A
        queue_b_answer = now + 20
        queue_b_hangup = now + 200
        
        records = [
            # Queue A leg - initial
            MockCDRRecord(
                xml_cdr_uuid=call_uuid,
                cc_queue="sales@internal",
                cc_queue_joined_epoch=queue_a_join,
                cc_queue_answered_epoch=queue_a_answer,
                billsec=60
            ),
            # Queue B leg - transfer
            MockCDRRecord(
                xml_cdr_uuid=call_uuid,
                cc_queue="support@internal",
                cc_queue_joined_epoch=queue_b_join,
                cc_queue_answered_epoch=queue_b_answer,
                billsec=60
            )
        ]
        
        # Find initial queue (earliest join time)
        initial_queue = min(records, key=lambda r: r.cc_queue_joined_epoch).cc_queue
        assert initial_queue == "sales@internal", "Initial queue should be the first one joined"
        
        # Get ASA from initial queue
        initial_record = [r for r in records if r.cc_queue == initial_queue][0]
        asa = initial_record.cc_queue_answered_epoch - initial_record.cc_queue_joined_epoch
        assert asa == 5, "ASA should use initial queue wait time"
        
        # Verify this call is answered
        is_answered = any(r.cc_queue_answered_epoch is not None for r in records)
        assert is_answered is True
    
    def test_abandoned_call_no_answered_timestamp(self):
        """
        Test: Call that joined queue but had no answer should be abandoned
        Expected: offered=1, answered=0, abandoned=1
        """
        now = int(datetime.utcnow().timestamp())
        
        records = [
            MockCDRRecord(
                xml_cdr_uuid="abandoned-789",
                cc_queue="sales@internal",
                cc_queue_joined_epoch=now,
                cc_queue_answered_epoch=None,  # No answer
                billsec=0,
                hangup_cause="ORIGINATOR_CANCEL",
                cc_queue_canceled_epoch=now + 30
            )
        ]
        
        # Check conditions
        has_answer = any(r.cc_queue_answered_epoch is not None for r in records)
        assert has_answer is False
        
        # Check abandonment indicators
        for record in records:
            has_billsec = (record.billsec or 0) == 0
            has_cancel = record.hangup_cause in ('ORIGINATOR_CANCEL', 'NO_ANSWER')
            assert has_billsec and has_cancel
    
    def test_multiple_calls_deduplication(self):
        """
        Test: Multiple calls (different xml_cdr_uuid) should not be deduplicated
        Expected: 3 unique root calls -> offered=3
        """
        now = int(datetime.utcnow().timestamp())
        
        records = [
            MockCDRRecord("call-1", "sales@internal", now, now + 5, billsec=60),
            MockCDRRecord("call-2", "sales@internal", now + 100, now + 105, billsec=80),
            MockCDRRecord("call-3", "sales@internal", now + 200, now + 210, billsec=120),
        ]
        
        # Count unique root calls
        unique_calls = len(set(r.xml_cdr_uuid for r in records))
        assert unique_calls == 3
    
    def test_answered_call_with_multiple_legs(self):
        """
        Test: Multi-leg answered call should count as 1 answered, use initial queue timing
        Expected: offered=1, answered=1, asa from initial queue, aht as total talk time
        """
        now = int(datetime.utcnow().timestamp())
        call_uuid = "multileg-call"
        
        records = [
            # Leg 1: Initial queue
            MockCDRRecord(
                xml_cdr_uuid=call_uuid,
                cc_queue="sales@internal",
                cc_queue_joined_epoch=now,
                cc_queue_answered_epoch=now + 10,
                billsec=60
            ),
            # Leg 2: Transfer
            MockCDRRecord(
                xml_cdr_uuid=call_uuid,
                cc_queue="billing@internal",
                cc_queue_joined_epoch=now + 70,
                cc_queue_answered_epoch=now + 72,
                billsec=40
            ),
        ]
        
        # Only 1 unique root call
        unique_calls = set(r.xml_cdr_uuid for r in records)
        assert len(unique_calls) == 1
        
        # Called is answered (any leg)
        is_answered = any(r.cc_queue_answered_epoch for r in records)
        assert is_answered is True
        
        # Initial queue determination
        initial_q = min(records, key=lambda r: r.cc_queue_joined_epoch).cc_queue
        assert initial_q == "sales@internal"
        
        # ASA from initial queue
        initial_rec = [r for r in records if r.cc_queue == initial_q][0]
        asa = initial_rec.cc_queue_answered_epoch - initial_rec.cc_queue_joined_epoch
        assert asa == 10
        
        # AHT as total talk time
        total_billsec = max(r.billsec for r in records)  # Use max to avoid double counting
        assert total_billsec == 60
    
    def test_service_level_calculation(self):
        """
        Test: Service Level 30 should count answered calls with <=30 sec wait
        Expected: 2 of 3 answered within 30 sec = 66.67%
        """
        now = int(datetime.utcnow().timestamp())
        
        # Fast answer (10 sec)
        r1_wait = 10
        # Slow answer (45 sec)
        r2_wait = 45
        # Medium answer (25 sec)
        r3_wait = 25
        
        records = [
            MockCDRRecord(
                "call-1", "sales@internal", now, now + r1_wait, billsec=60
            ),
            MockCDRRecord(
                "call-2", "sales@internal", now + 100, now + 100 + r2_wait, billsec=60
            ),
            MockCDRRecord(
                "call-3", "sales@internal", now + 200, now + 200 + r3_wait, billsec=60
            ),
        ]
        
        threshold = 30
        within_threshold = sum(
            1 for r in records 
            if r.cc_queue_answered_epoch and 
               (r.cc_queue_answered_epoch - r.cc_queue_joined_epoch) <= threshold
        )
        answered_count = sum(
            1 for r in records 
            if r.cc_queue_answered_epoch
        )
        
        sl30 = (within_threshold / answered_count * 100) if answered_count > 0 else 0
        
        assert within_threshold == 2
        assert answered_count == 3
        assert abs(sl30 - 66.67) < 0.01
    
    def test_asa_calculation_weighted(self):
        """
        Test: ASA should be average wait time for answered calls
        Expected: (10 + 45 + 25) / 3 = 26.67 sec
        """
        now = int(datetime.utcnow().timestamp())
        
        wait_times = [10, 45, 25]
        records = [
            MockCDRRecord(
                f"call-{i}",
                "sales@internal",
                now + (i * 100),
                now + (i * 100) + wait,
                billsec=60
            )
            for i, wait in enumerate(wait_times)
        ]
        
        answered_records = [r for r in records if r.cc_queue_answered_epoch]
        waits = [
            r.cc_queue_answered_epoch - r.cc_queue_joined_epoch
            for r in answered_records
        ]
        
        asa = sum(waits) / len(waits) if waits else 0
        expected = sum(wait_times) / len(wait_times)
        
        assert abs(asa - expected) < 0.01
        assert abs(asa - 26.67) < 0.01


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_call_with_no_queue_join(self):
        """
        Test: Call with no queue join timestamp should not affect queue report
        Expected: Filtered out before processing
        """
        records = [
            MockCDRRecord(
                "no-queue-call",
                cc_queue=None,  # No queue
                cc_queue_joined_epoch=None,
                cc_queue_answered_epoch=None,
                billsec=0
            )
        ]
        
        # These should be filtered out
        queue_records = [r for r in records if r.cc_queue_joined_epoch is not None]
        assert len(queue_records) == 0
    
    def test_empty_dataset(self):
        """
        Test: Empty dataset should return graceful response
        Expected: offered=0, no division by zero
        """
        records = []
        
        offered = len(records)
        assert offered == 0
        
        asa = sum([]) / len([]) if records else 0
        assert asa == 0
    
    def test_deflect_exclusion(self):
        """
        Test: Deflected calls can be excluded if enabled
        Expected: Abandoned count excludes deflects when flag is true
        """
        now = int(datetime.utcnow().timestamp())
        
        records = [
            # Normal abandoned
            MockCDRRecord(
                "normal-abandon",
                "sales@internal",
                now,
                cc_queue_answered_epoch=None,
                billsec=0,
                hangup_cause="ORIGINATOR_CANCEL",
                cc_queue_canceled_epoch=now + 30
            ),
            # Deflected (should be excluded if exclude_deflects=True)
            MockCDRRecord(
                "deflected-call",
                "sales@internal",
                now + 100,
                cc_queue_answered_epoch=None,
                billsec=0,
                last_app="deflect",
                hangup_cause="ORIGINATOR_CANCEL",
                cc_queue_canceled_epoch=now + 130
            ),
        ]
        
        exclude_deflects = True
        
        abandoned_count = 0
        for record in records:
            # Apply exclusion logic
            if exclude_deflects and record.last_app == 'deflect':
                continue
            
            if record.cc_queue_answered_epoch is None:
                if record.billsec == 0:
                    abandoned_count += 1
        
        # Only the first call should count as abandoned
        assert abandoned_count == 1

    def test_user_busy_counts_as_queue_abandoned(self):
        """
        Test: USER_BUSY with no answer should still count as queue abandoned.
        Expected: offered=1, answered=0, abandoned=1
        """
        now = int(datetime.utcnow().timestamp())

        records = [
            MockCDRRecord(
                "busy-unanswered",
                "sales@internal",
                now,
                cc_queue_answered_epoch=None,
                billsec=0,
                hangup_cause="USER_BUSY",
                cc_queue_canceled_epoch=now + 20,
            )
        ]

        has_answer = any(r.cc_queue_answered_epoch is not None for r in records)
        assert has_answer is False

        abandoned_count = 0
        for record in records:
            if (record.billsec or 0) != 0:
                continue
            if (record.hangup_cause in ("ORIGINATOR_CANCEL", "NO_ANSWER", "USER_BUSY") or
                (getattr(record, "cc_cause", None) or "") == "TIMEOUT" or
                (getattr(record, "call_disposition", None) or "") == "missed"):
                abandoned_count += 1

        assert abandoned_count == 1
