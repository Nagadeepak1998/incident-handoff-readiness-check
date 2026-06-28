#!/usr/bin/env python3
"""Check whether incident handoff notes are ready for the next owner."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


OPEN_STATUSES = {"investigating", "mitigating", "monitoring"}
CLOSED_STATUSES = {"resolved", "closed"}
COMMS_STATUSES = {"not_needed", "drafted", "sent", "scheduled"}


@dataclass(frozen=True)
class Finding:
    severity: str
    incident: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.incident}: {self.message}"


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_list_items(value: Any) -> bool:
    return isinstance(value, list) and any(has_text(item) for item in value)


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def load_incidents(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}") from exc

    incidents = raw.get("incidents") if isinstance(raw, dict) else None
    if not isinstance(incidents, list):
        raise ValueError(f"{path}: expected top-level object with an incidents list")

    ids: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for index, incident in enumerate(incidents, start=1):
        if not isinstance(incident, dict):
            raise ValueError(f"{path}: incidents[{index}] must be an object")
        incident_id = incident.get("id")
        if not has_text(incident_id):
            raise ValueError(f"{path}: incidents[{index}] must include a non-empty string id")
        if incident_id in ids:
            raise ValueError(f"{path}: duplicate incident id {incident_id!r}")
        ids.add(incident_id)
        parsed.append(incident)
    return parsed


def review_timeline(incident: dict[str, Any], incident_id: str) -> list[Finding]:
    findings: list[Finding] = []
    started_at = parse_datetime(incident.get("started_at"))
    detected_at = parse_datetime(incident.get("detected_at"))
    resolved_at = parse_datetime(incident.get("resolved_at"))
    timeline_events = incident.get("timeline_events")

    if started_at is None:
        findings.append(Finding("HIGH", incident_id, "missing valid started_at timestamp"))
    if detected_at is None:
        findings.append(Finding("MEDIUM", incident_id, "missing valid detected_at timestamp"))
    elif started_at and detected_at < started_at:
        findings.append(Finding("HIGH", incident_id, "detected_at is before started_at"))

    if resolved_at and started_at and resolved_at < started_at:
        findings.append(Finding("HIGH", incident_id, "resolved_at is before started_at"))

    if not isinstance(timeline_events, list) or len(timeline_events) < 2:
        findings.append(Finding("MEDIUM", incident_id, "handoff needs at least two timeline events"))
        return findings

    valid_events = 0
    for event in timeline_events:
        if isinstance(event, dict) and parse_datetime(event.get("at")) and has_text(event.get("note")):
            valid_events += 1
    if valid_events < 2:
        findings.append(Finding("MEDIUM", incident_id, "timeline events need valid at timestamps and notes"))

    return findings


def review_incident(incident: dict[str, Any]) -> list[Finding]:
    incident_id = str(incident["id"])
    findings = review_timeline(incident, incident_id)

    severity = str(incident.get("severity", "")).strip().lower()
    status = str(incident.get("status", "")).strip().lower()
    comms_status = str(incident.get("customer_comms_status", "")).strip().lower()

    if severity not in {"sev1", "sev2", "sev3", "sev4"}:
        findings.append(Finding("MEDIUM", incident_id, "severity should be one of sev1, sev2, sev3, or sev4"))

    if status not in OPEN_STATUSES | CLOSED_STATUSES:
        findings.append(Finding("HIGH", incident_id, "status is missing or not a supported handoff state"))

    if not has_text(incident.get("owner")):
        findings.append(Finding("HIGH", incident_id, "missing current owner"))

    if not has_text(incident.get("next_action")):
        findings.append(Finding("HIGH", incident_id, "missing next action for the receiving owner"))

    if status in OPEN_STATUSES and parse_datetime(incident.get("next_update_at")) is None:
        findings.append(Finding("MEDIUM", incident_id, "open incident needs a valid next_update_at timestamp"))

    if not has_text(incident.get("impact_summary")):
        findings.append(Finding("HIGH", incident_id, "missing customer or service impact summary"))

    if not has_list_items(incident.get("affected_services")):
        findings.append(Finding("MEDIUM", incident_id, "missing affected services"))

    if not has_text(incident.get("mitigation")):
        findings.append(Finding("HIGH", incident_id, "missing mitigation or current containment step"))

    if not has_list_items(incident.get("evidence_links")):
        findings.append(Finding("MEDIUM", incident_id, "missing evidence links for dashboards, logs, or tickets"))

    if severity in {"sev1", "sev2"} and comms_status not in COMMS_STATUSES:
        findings.append(Finding("MEDIUM", incident_id, "sev1/sev2 incidents need customer_comms_status"))

    if status in CLOSED_STATUSES and not has_text(incident.get("follow_up")):
        findings.append(Finding("MEDIUM", incident_id, "closed incidents need a follow-up or postmortem note"))

    if status in OPEN_STATUSES and not has_text(incident.get("rollback_plan")):
        findings.append(Finding("MEDIUM", incident_id, "open incidents need a rollback or fallback plan"))

    return findings


def review_incidents(incidents: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    for incident in sorted(incidents, key=lambda item: str(item["id"])):
        findings.extend(review_incident(incident))
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review incident handoff JSON for missing operational context."
    )
    parser.add_argument("handoff", type=Path, help="Incident handoff JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        incidents = load_incidents(args.handoff)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    findings = review_incidents(incidents)
    if not findings:
        print("PASS: incident handoff is ready for the next owner")
        return 0

    print(f"FLAGGED: {len(findings)} incident handoff issue(s) detected")
    for finding in findings:
        print(f"- {finding.render()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
