import pytest

from detailed.request_validation import RequestValidationError, expect_list_payload, require_non_empty_string


def test_require_non_empty_string_returns_trimmed_value():
    assert require_non_empty_string({"name": "  abc  "}, "name") == "abc"


def test_require_non_empty_string_raises_for_missing_value():
    with pytest.raises(RequestValidationError) as exc:
        require_non_empty_string({"name": "   "}, "name", code="name_required")
    assert exc.value.code == "name_required"


def test_expect_list_payload_accepts_list():
    payload = expect_list_payload([1, 2, 3])
    assert payload == [1, 2, 3]


def test_expect_list_payload_rejects_non_list():
    with pytest.raises(RequestValidationError) as exc:
        expect_list_payload({"value": 1}, message="Expected list")
    assert exc.value.message == "Expected list"
