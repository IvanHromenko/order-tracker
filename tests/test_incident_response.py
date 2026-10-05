import pytest
from fastapi.testclient import TestClient

from incident_response import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "incidents.sqlite3")
    with TestClient(main.app) as test_client:
        yield test_client


def test_firing_alert_is_saved_and_starts_assistant(client, monkeypatch):
    started = []
    monkeypatch.setattr(main, "run_assistant", lambda incident_id: started.append(incident_id))
    payload = {
        "status": "firing",
        "commonAnnotations": {"endpoint": "GET /api/orders/{order_id}"},
        "alerts": [
            {
                "status": "firing",
                "fingerprint": "5xx-alert-1",
                "startsAt": "2026-10-05T12:00:00Z",
                "labels": {"alertname": "Order Tracker API 5xx responses"},
                "annotations": {
                    "logs": [{"timestamp": "2026-10-05T12:01:00Z", "message": "database unavailable"}],
                    "traces": [{"traceID": "trace-123", "spanID": "span-456"}],
                },
            }
        ],
    }

    response = client.post("/alerts", json=payload)

    assert response.status_code == 202
    assert response.json()["assistant_queued"] == 1
    incident_id = response.json()["incident_ids"][0]
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["endpoint"] == "GET /api/orders/{order_id}"
    assert incident["logs"][0]["message"] == "database unavailable"
    assert incident["traces"][0]["traceID"] == "trace-123"
    assert incident["status"] == "firing"
    assert started == [incident_id]


def test_duplicate_firing_alert_does_not_start_second_assistant(client, monkeypatch):
    started = []
    monkeypatch.setattr(main, "run_assistant", lambda incident_id: started.append(incident_id))
    payload = {
        "alerts": [
            {
                "status": "firing",
                "fingerprint": "same-alert",
                "startsAt": "2026-10-05T12:00:00Z",
                "labels": {"alertname": "test"},
            }
        ]
    }

    first = client.post("/alerts", json=payload).json()
    second = client.post("/alerts", json=payload).json()

    assert first["incident_ids"] == second["incident_ids"]
    assert first["assistant_queued"] == 1
    assert second["assistant_queued"] == 0
    assert started == first["incident_ids"]


def test_failed_firing_alert_can_be_retried(client, monkeypatch):
    started = []
    monkeypatch.setattr(main, "run_assistant", lambda incident_id: started.append(incident_id))
    payload = {
        "alerts": [
            {
                "status": "firing",
                "fingerprint": "retry-alert",
                "startsAt": "2026-10-05T12:00:00Z",
            }
        ]
    }

    first = client.post("/alerts", json=payload).json()
    main.update_assistant(first["incident_ids"][0], "failed", error="No auth")
    retry = client.post("/alerts", json=payload).json()

    assert first["incident_ids"] == retry["incident_ids"]
    assert retry["assistant_queued"] == 1
    assert started == first["incident_ids"] * 2


def test_resolved_alert_updates_incident_without_starting_assistant(client, monkeypatch):
    started = []
    monkeypatch.setattr(main, "run_assistant", lambda incident_id: started.append(incident_id))
    base_alert = {
        "fingerprint": "resolved-alert",
        "startsAt": "2026-10-05T12:00:00Z",
        "labels": {"alertname": "test"},
    }

    firing = client.post("/alerts", json={"alerts": [{**base_alert, "status": "firing"}]}).json()
    resolved = client.post("/alerts", json={"alerts": [{**base_alert, "status": "resolved"}]}).json()
    incident = client.get(f"/incidents/{firing['incident_ids'][0]}").json()

    assert resolved["assistant_queued"] == 0
    assert incident["status"] == "resolved"
    assert incident["resolved_at"] is not None
    assert started == firing["incident_ids"]


def test_alert_payload_requires_alerts_array(client):
    response = client.post("/alerts", json={"status": "firing"})

    assert response.status_code == 422


def test_assistant_uses_headless_autopilot_command(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "incidents.sqlite3")
    monkeypatch.setattr(main, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setenv("ASSISTANT_COMMAND_JSON", "")
    main.initialize_database()
    incident_id, _ = main.save_alert(
        {
            "status": "firing",
            "fingerprint": "headless-test",
            "startsAt": "2026-10-05T12:00:00Z",
        },
        {"alerts": []},
    )
    captured = {}

    class Process:
        pid = 123

        def wait(self):
            return 0

    class InlineThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(main.threading, "Thread", InlineThread)

    main.run_assistant(incident_id)

    assert captured["args"][:2] == ["copilot", "-p"]
    assert "--autopilot" in captured["args"]
    assert "--max-autopilot-continues=5" in captured["args"]
    assert "--no-ask-user" in captured["args"]
    assert captured["kwargs"]["cwd"] == tmp_path
    assert main.get_incident(incident_id)["assistant_status"] == "completed"