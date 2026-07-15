.PHONY: test smoke report

PYTHON ?= python3

test:
	$(PYTHON) -m py_compile incident_handoff_check.py tests/test_incident_handoff_check.py
	PYTHONPATH=. $(PYTHON) -m unittest discover -s tests

smoke:
	$(PYTHON) incident_handoff_check.py samples/safe_handoff.json
	$(PYTHON) incident_handoff_check.py samples/risky_handoff.json || test $$? -eq 1

report:
	$(PYTHON) incident_handoff_check.py samples/risky_handoff.json \
		--json-out reports/risky_handoff_report.json \
		--markdown-out reports/risky_handoff_report.md \
		--metrics-out reports/risky_handoff_metrics.prom || test $$? -eq 1
