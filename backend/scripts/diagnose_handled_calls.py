"""
Diagnostic: why is handled_calls count lower than expected for an agent?

Prints a breakdown of:
1. Raw CDR rows attributed to the agent in the date window
2. How many are classified as handled / missed / other
3. How many unique interaction keys there are (the final count used)
4. Any interaction key collisions (multiple handled records sharing the same key)
5. Direction breakdown
6. Records where is_handled=False despite the call being answered (potential under-count)
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.database import SessionLocal
from app.models import CDRRecord, Agent
from app.api.agent_performance import build_agent_resolution_context, resolve_agent_identity
from app.utils.agent_performance_utils import (
    normalize_agent_id,
    get_agent_interaction_key,
    is_handled,
    is_excluded,
    get_agent_record_rank,
    _has_call_center_context,
)

# ── Config ───────────────────────────────────────────────────────────────────
AGENT_NAME_SEARCH = "darian"          # case-insensitive substring match
# Match the UI "last 7 days": start of day, 6 calendar days ago through end of today (UTC)
DAYS_BACK = 6
INCLUDE_OUTBOUND = False               # match the default UI setting
EXCLUDE_DEFLECTS = True
# ─────────────────────────────────────────────────────────────────────────────


def main():
    db = SessionLocal()

    # Find agent
    agents = db.query(Agent).all()
    matched = [a for a in agents if AGENT_NAME_SEARCH.lower() in (a.agent_name or "").lower()]
    if not matched:
        print(f"No agent found matching '{AGENT_NAME_SEARCH}'")
        db.close()
        return

    for agent in matched:
        print(f"\n{'='*70}")
        print(f"Agent: {agent.agent_name}  (uuid={agent.agent_uuid})")
        print(f"{'='*70}")

        # Date window — same logic as get_time_window()
        now = datetime.now(timezone.utc)
        # Mirror the frontend "last_7" preset: start of day, 6 days ago → end of today
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=DAYS_BACK)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start_epoch = int(start_dt.timestamp())
        end_epoch = int(end_dt.timestamp())
        print(f"Window: {start_dt.isoformat()} → {end_dt.isoformat()} UTC")

        # Pull all CDR rows attributed to this agent (no direction filter — we
        # want to see everything so we can spot what's being excluded)
        from sqlalchemy import or_
        rows = (
            db.query(CDRRecord)
            .filter(
                CDRRecord.start_epoch >= start_epoch,
                CDRRecord.start_epoch <= end_epoch,
                or_(
                    CDRRecord.cc_agent == agent.agent_uuid,
                    CDRRecord.cc_agent_uuid == agent.agent_uuid,
                    CDRRecord.extension_uuid == agent.agent_uuid,
                ),
            )
            .all()
        )

        print(f"\nTotal raw CDR rows (all directions, no other filters): {len(rows)}")

        direction_counts = defaultdict(int)
        handled_by_direction = defaultdict(int)
        not_handled_answered = []      # answered but is_handled returned False
        excluded_count = 0
        handled_keys: dict = {}        # interaction_key → best record
        raw_handled = 0

        for r in rows:
            direction = (r.direction or "").lower()
            direction_counts[direction] += 1

            if EXCLUDE_DEFLECTS and is_excluded(r):
                excluded_count += 1
                continue

            # Skip non-inbound when simulating include_outbound=False
            if not INCLUDE_OUTBOUND and direction != "inbound":
                continue

            if is_handled(r):
                raw_handled += 1
                handled_by_direction[direction] += 1
                key = get_agent_interaction_key(r)
                if key:
                    existing = handled_keys.get(key)
                    if existing is None or get_agent_record_rank(r) > get_agent_record_rank(existing):
                        handled_keys[key] = r

            else:
                # Not handled — but was the call actually answered?
                answered = any([
                    r.cc_queue_answered_epoch,
                    r.answer_epoch,
                    (r.billsec or 0) > 0,
                    r.status == "answered",
                ])
                if answered:
                    not_handled_answered.append(r)

        print(f"\nDirection breakdown (all rows, before filters):")
        for d, cnt in sorted(direction_counts.items()):
            print(f"  {d or '(empty)'}: {cnt}")

        print(f"\nAfter applying direction filter (include_outbound={INCLUDE_OUTBOUND}):")
        print(f"  is_handled=True records : {raw_handled}")
        print(f"  Excluded (deflects)      : {excluded_count}")

        print(f"\nHandled breakdown by direction:")
        for d, cnt in sorted(handled_by_direction.items()):
            print(f"  {d or '(empty)'}: {cnt}")

        # ── Collision analysis ───────────────────────────────────────────────
        key_hits: dict = defaultdict(int)
        from sqlalchemy import or_
        for r in rows:
            direction = (r.direction or "").lower()
            if not INCLUDE_OUTBOUND and direction != "inbound":
                continue
            if EXCLUDE_DEFLECTS and is_excluded(r):
                continue
            if is_handled(r):
                key = get_agent_interaction_key(r)
                if key:
                    key_hits[key] += 1

        collisions = {k: v for k, v in key_hits.items() if v > 1}
        print(f"\nUnique interaction keys (= final handled_calls count) : {len(handled_keys)}")
        print(f"Interaction key collisions (multiple handled rows → 1)  : {len(collisions)}")
        if collisions:
            print("  Colliding keys:")
            for k, cnt in list(collisions.items())[:10]:
                print(f"    {k}  → {cnt} rows collapsed to 1")

        # ── Rows that are answered but not counted ────────────────────────────
        print(f"\nRecords classified as NOT handled but appear answered : {len(not_handled_answered)}")
        if not_handled_answered:
            print("  (first 10 shown)")
            for r in not_handled_answered[:10]:
                print(
                    f"  uuid={r.xml_cdr_uuid[:8]}.. dir={r.direction} "
                    f"billsec={r.billsec} answer_epoch={r.answer_epoch} "
                    f"cc_queue_ans={r.cc_queue_answered_epoch} status={r.status} "
                    f"cc_context={_has_call_center_context(r)} "
                    f"hangup={r.hangup_cause}"
                )

        # ── Rows dropped for not-inbound direction ───────────────────────────
        dropped_direction = [
            r for r in rows
            if not INCLUDE_OUTBOUND and (r.direction or "").lower() != "inbound"
            and is_handled(r)  # these WOULD be handled but are direction-filtered
        ]
        print(f"\nHandled rows dropped solely by direction filter       : {len(dropped_direction)}")
        if dropped_direction:
            print("  (first 10 shown)")
            for r in dropped_direction[:10]:
                print(
                    f"  uuid={r.xml_cdr_uuid[:8]}.. dir={r.direction} "
                    f"billsec={r.billsec} cc_side={r.cc_side} leg={r.leg} "
                    f"cc_agent={r.cc_agent}"
                )

        print(f"\n→ UI reported handled_calls (simulated): {len(handled_keys)}")

        # ── Part 2: use the REAL leaderboard resolution path ─────────────────
        print(f"\n{'─'*70}")
        print("Part 2: actual resolve_agent_identity() attribution")
        print(f"{'─'*70}")
        resolution_ctx = build_agent_resolution_context(db, enabled_only=False)
        alias_to_agent_id = resolution_ctx["alias_to_agent_id"]
        agent_name_map = resolution_ctx["agent_name_map"]

        # Also look up Darian's Extension UUID (separate from agent UUID)
        from app.models import Extension as ExtModel
        ext_rec = (
            db.query(ExtModel)
            .filter(
                ExtModel.extension == agent.extension if agent.extension else False
            )
            .first()
        )
        darian_ext_uuid = str(ext_rec.extension_uuid).strip() if ext_rec and ext_rec.extension_uuid else None
        print(f"Agent extension number           : {agent.extension}")
        print(f"Matching Extension UUID          : {darian_ext_uuid}")

        # Find Darian's canonical ID as seen by the resolution context
        darian_canonical = alias_to_agent_id.get(agent.agent_uuid, agent.agent_uuid)
        print(f"Darian's agent_uuid              : {agent.agent_uuid}")
        print(f"Canonical ID via alias_to_agent_id: {darian_canonical}")
        if darian_canonical != agent.agent_uuid:
            print("  ⚠  UUID is an ALIAS → records will be attributed to a different canonical ID!")

        # Check Extension UUID mapping
        if darian_ext_uuid:
            ext_canonical = alias_to_agent_id.get(darian_ext_uuid)
            if ext_canonical:
                print(f"Extension UUID maps to canonical : {ext_canonical}")
                if ext_canonical != darian_canonical:
                    print("  ⚠  Extension UUID maps to a DIFFERENT canonical ID from agent UUID!")
            else:
                print("  ⚠  Extension UUID is NOT in alias_to_agent_id — those CDRs won't attribute to Darian!")

        # ── Part 3: full table scan (same as leaderboard) ────────────────────
        print(f"\n{'─'*70}")
        print("Part 3: full table scan matching exact leaderboard query")
        print(f"{'─'*70}")
        from sqlalchemy import or_
        full_rows = (
            db.query(CDRRecord)
            .filter(
                CDRRecord.start_epoch >= start_epoch,
                CDRRecord.start_epoch <= end_epoch,
                CDRRecord.direction == "inbound",
                or_(
                    CDRRecord.cc_agent_uuid.isnot(None),
                    CDRRecord.cc_agent.isnot(None),
                    CDRRecord.extension_uuid.isnot(None),
                ),
            )
            .all()
        )
        print(f"Total inbound CDR rows in window (all agents): {len(full_rows)}")

        full_handled_keys: dict = {}
        for r in full_rows:
            if EXCLUDE_DEFLECTS and is_excluded(r):
                continue
            resolved_id, _ = resolve_agent_identity(r, resolution_ctx)
            if resolved_id != darian_canonical:
                continue
            if not is_handled(r):
                continue
            key = get_agent_interaction_key(r)
            if not key:
                continue
            existing = full_handled_keys.get(key)
            if existing is None or get_agent_record_rank(r) > get_agent_record_rank(existing):
                full_handled_keys[key] = r

        print(f"Handled calls for Darian (exact leaderboard logic): {len(full_handled_keys)}")
        print(f"\n→ This is what the UI should show for last 7 days: {len(full_handled_keys)}")

        # Re-run the leaderboard loop on the same raw rows using the real resolver
        real_handled_keys: dict = {}
        redirected: list = []  # handled rows that resolve to a DIFFERENT canonical ID

        for r in rows:
            direction = (r.direction or "").lower()
            if not INCLUDE_OUTBOUND and direction != "inbound":
                continue
            if EXCLUDE_DEFLECTS and is_excluded(r):
                continue

            resolved_id, source = resolve_agent_identity(r, resolution_ctx)
            if resolved_id is None:
                continue

            if not is_handled(r):
                continue

            key = get_agent_interaction_key(r)
            if not key:
                continue

            if resolved_id == darian_canonical:
                existing = real_handled_keys.get(key)
                if existing is None or get_agent_record_rank(r) > get_agent_record_rank(existing):
                    real_handled_keys[key] = r
            else:
                # This handled record has cc_agent=Darian but resolves elsewhere
                redirected.append((r, resolved_id, source))

        print(f"\nHandled records attributed to Darian's canonical ID : {len(real_handled_keys)}")
        print(f"Handled records redirected to another canonical ID  : {len(redirected)}")

        if redirected:
            other_ids: dict = defaultdict(int)
            for r, rid, src in redirected:
                other_name = agent_name_map.get(rid, rid)
                other_ids[f"{other_name} ({rid[:8]}..  via {src})"] += 1
            print("  Redirected to:")
            for name_id, cnt in sorted(other_ids.items(), key=lambda x: -x[1]):
                print(f"    {cnt}× → {name_id}")

        print(f"\n→ leaderboard would show for Darian: {len(real_handled_keys)}")

    db.close()


if __name__ == "__main__":
    main()
