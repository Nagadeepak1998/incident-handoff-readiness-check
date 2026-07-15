import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from incident_handoff_check import (
    build_review_report,
    load_incidents,
    main,
    render_markdown_report,
    render_metrics_report,
    review_incidents,
)


class IncidentHandoffCheckTests(unittest.TestCase):
    def test_ready_open_incident_has_no_findings(self):
        incidents = [
            {
                "id": "INC-1042",
                "severity": "sev2",
                "status": "monitoring",
                "owner": "payments-platform",
                "started_at": "2026-06-26T08:10:00-07:00",
                "detected_at": "2026-06-26T08:14:00-07:00",
                "next_update_at": "2026-06-26T10:30:00-07:00",
                "impact_summary": "Checkout latency increased for a small set of card payments.",
                "affected_services": ["checkout-api", "payment-worker"],
                "mitigation": "Shifted traffic away from the degraded processor route.",
                "next_action": "Watch error rate for 30 minutes before restoring normal routing.",
                "rollback_plan": "Keep alternate processor route active if errors rise above 2%.",
                "customer_comms_status": "sent",
                "evidence_links": ["https://dashboards.example/incidents/INC-1042"],
                "timeline_events": [
                    {"at": "2026-06-26T08:14:00-07:00", "note": "Alert fired for checkout latency."},
                    {"at": "2026-06-26T08:28:00-07:00", "note": "Traffic shifted to alternate route."},
                ],
            }
        ]

        findings = review_incidents(incidents)

        self.assertEqual([], findings)

    def test_risky_incident_reports_expected_findings(self):
        incidents = [
            {
                "id": "INC-1043",
                "severity": "sev2",
                "status": "investigating",
                "owner": "",
                "started_at": "2026-06-26T09:10:00-07:00",
                "detected_at": "2026-06-26T09:05:00-07:00",
                "impact_summary": "",
                "affected_services": [],
                "mitigation": "",
                "next_action": "",
                "customer_comms_status": "",
                "evidence_links": [],
                "timeline_events": [{"at": "2026-06-26T09:05:00-07:00", "note": "Alert fired."}],
            }
        ]

        findings = review_incidents(incidents)
        messages = [finding.message for finding in findings]

        self.assertEqual(11, len(findings))
        self.assertIn("detected_at is before started_at", messages)
        self.assertIn("handoff needs at least two timeline events", messages)
        self.assertIn("missing current owner", messages)
        self.assertIn("missing next action for the receiving owner", messages)
        self.assertIn("open incident needs a valid next_update_at timestamp", messages)
        self.assertIn("missing customer or service impact summary", messages)
        self.assertIn("missing affected services", messages)
        self.assertIn("missing mitigation or current containment step", messages)
        self.assertIn("missing evidence links for dashboards, logs, or tickets", messages)
        self.assertIn("sev1/sev2 incidents need customer_comms_status", messages)
        self.assertIn("open incidents need a rollback or fallback plan", messages)

    def test_loader_rejects_duplicate_incident_ids(self):
        fixture = tempfile.NamedTemporaryFile(mode="w+", suffix=".json")
        try:
            fixture.write('{"incidents": [{"id": "INC-1"}, {"id": "INC-1"}]}')
            fixture.flush()

            with self.assertRaisesRegex(ValueError, "duplicate incident id"):
                load_incidents(Path(fixture.name))
        finally:
            fixture.close()

    def test_review_report_summarizes_findings_and_owners(self):
        incidents = [
            {
                "id": "INC-1043",
                "severity": "sev2",
                "status": "investigating",
                "owner": "",
                "started_at": "2026-06-26T09:10:00-07:00",
                "detected_at": "2026-06-26T09:05:00-07:00",
                "impact_summary": "",
                "affected_services": [],
                "mitigation": "",
                "next_action": "",
                "customer_comms_status": "",
                "evidence_links": [],
                "timeline_events": [{"at": "2026-06-26T09:05:00-07:00", "note": "Alert fired."}],
            }
        ]

        report = build_review_report(incidents)

        self.assertEqual("flagged", report.status)
        self.assertEqual(1, report.incident_count)
        self.assertEqual(11, report.finding_count)
        self.assertEqual(5, report.severity_counts["HIGH"])
        self.assertEqual(6, report.severity_counts["MEDIUM"])
        self.assertEqual({"unassigned": 1}, report.owner_counts)

    def test_markdown_report_renders_reviewer_summary(self):
        report = build_review_report(
            [
                {
                    "id": "INC-1042",
                    "severity": "sev2",
                    "status": "monitoring",
                    "owner": "payments-platform",
                    "started_at": "2026-06-26T08:10:00-07:00",
                    "detected_at": "2026-06-26T08:14:00-07:00",
                    "next_update_at": "2026-06-26T10:30:00-07:00",
                    "impact_summary": "Checkout latency increased.",
                    "affected_services": ["checkout-api"],
                    "mitigation": "Shifted traffic away from the degraded route.",
                    "next_action": "Watch error rate for 30 minutes.",
                    "rollback_plan": "Keep alternate route active.",
                    "customer_comms_status": "sent",
                    "evidence_links": ["https://dashboards.example/incidents/INC-1042"],
                    "timeline_events": [
                        {"at": "2026-06-26T08:14:00-07:00", "note": "Alert fired."},
                        {"at": "2026-06-26T08:28:00-07:00", "note": "Traffic shifted."},
                    ],
                }
            ]
        )

        markdown = render_markdown_report(report)

        self.assertIn("# Incident Handoff Readiness Report", markdown)
        self.assertIn("- Status: `pass`", markdown)
        self.assertIn("| payments-platform | 1 |", markdown)
        self.assertIn("No readiness gaps detected.", markdown)

    def test_metrics_report_renders_prometheus_style_counts(self):
        report = build_review_report(
            [
                {
                    "id": "INC-1043",
                    "severity": "sev2",
                    "status": "investigating",
                    "owner": "",
                    "started_at": "2026-06-26T09:10:00-07:00",
                    "detected_at": "2026-06-26T09:05:00-07:00",
                    "impact_summary": "",
                    "affected_services": [],
                    "mitigation": "",
                    "next_action": "",
                    "customer_comms_status": "",
                    "evidence_links": [],
                    "timeline_events": [{"at": "2026-06-26T09:05:00-07:00", "note": "Alert fired."}],
                }
            ]
        )

        metrics = render_metrics_report(report)

        self.assertIn('incident_handoff_reviews_total{status="flagged"} 1', metrics)
        self.assertIn("incident_handoff_incidents_reviewed 1", metrics)
        self.assertIn('incident_handoff_findings_total{severity="HIGH"} 5', metrics)
        self.assertIn('incident_handoff_findings_total{severity="MEDIUM"} 6', metrics)

    def test_cli_writes_json_markdown_and_metrics_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            handoff_path = tmp_path / "handoff.json"
            json_path = tmp_path / "report.json"
            markdown_path = tmp_path / "report.md"
            metrics_path = tmp_path / "metrics.prom"
            handoff_path.write_text(
                '{"incidents": [{"id": "INC-1044", "severity": "sev4", "status": "closed", '
                '"owner": "platform", "started_at": "2026-06-26T08:10:00-07:00", '
                '"detected_at": "2026-06-26T08:12:00-07:00", "resolved_at": '
                '"2026-06-26T08:40:00-07:00", "impact_summary": "No customer impact.", '
                '"affected_services": ["worker"], "mitigation": "Retried failed jobs.", '
                '"next_action": "Close duplicate alert.", "follow_up": "Logged in weekly review.", '
                '"evidence_links": ["https://dashboards.example/incidents/INC-1044"], '
                '"timeline_events": [{"at": "2026-06-26T08:12:00-07:00", "note": "Alert fired."}, '
                '{"at": "2026-06-26T08:40:00-07:00", "note": "Jobs recovered."}]}]}',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        str(handoff_path),
                        "--json-out",
                        str(json_path),
                        "--markdown-out",
                        str(markdown_path),
                        "--metrics-out",
                        str(metrics_path),
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertIn('"status": "pass"', json_path.read_text(encoding="utf-8"))
            self.assertIn("- Status: `pass`", markdown_path.read_text(encoding="utf-8"))
            self.assertIn('incident_handoff_reviews_total{status="pass"} 1', metrics_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
