from pathlib import Path
import tempfile
import unittest

from incident_handoff_check import load_incidents, review_incidents


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


if __name__ == "__main__":
    unittest.main()
