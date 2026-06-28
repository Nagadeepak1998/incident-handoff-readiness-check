FROM python:3.12-slim

WORKDIR /app
COPY . .

ENTRYPOINT ["python", "incident_handoff_check.py"]
CMD ["samples/safe_handoff.json"]
