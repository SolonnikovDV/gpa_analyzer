from flask import Flask

from detailed.api_contracts import api_error, api_ok, read_json_object


def test_api_ok_wraps_payload():
    app = Flask(__name__)
    with app.app_context():
        response = api_ok(data={"value": 1}, answer=42)
    payload = response.get_json()
    assert response.status_code == 200
    assert payload == {"ok": True, "data": {"value": 1}, "answer": 42}


def test_api_error_exposes_standard_fields():
    app = Flask(__name__)
    with app.app_context():
        response = api_error("bad_request", "Broken", http_status=422, details={"field": "name"})
    payload = response.get_json()
    assert response.status_code == 422
    assert payload["ok"] is False
    assert payload["error"] == "Broken"
    assert payload["message"] == "Broken"
    assert payload["error_code"] == "bad_request"
    assert payload["error_details"] == {"field": "name"}


def test_read_json_object_returns_dict_payload():
    app = Flask(__name__)
    with app.test_request_context(json={"value": 3}):
        payload = read_json_object()
    assert payload == {"value": 3}


def test_read_json_object_rejects_non_object_payload():
    app = Flask(__name__)
    with app.test_request_context(json=["not", "an", "object"]):
        payload = read_json_object()
    assert payload == {}
