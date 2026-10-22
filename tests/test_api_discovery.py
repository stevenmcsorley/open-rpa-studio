import json

import pytest

from openrpa.api_discovery import discover_response


def test_discovers_observed_array_and_scalar_paths_without_returning_values():
    body = json.dumps({"data": {"items": [
        {"order/id": "private-order-value", "customer": {"name": "private-name"},
         "amount": 12.5, "access_token": "must-not-leak", "tags": ["a"]},
        {"order/id": "another-order", "customer": {"name": "another-name"}, "amount": None},
    ]}})

    result = discover_response(body)

    candidate = next(item for item in result["candidates"] if item["itemsPointer"] == "/data/items")
    assert candidate["observedRows"] == 2
    assert candidate["sampledRows"] == 2
    assert {field["path"] for field in candidate["fields"]} == {"/amount", "/customer/name", "/order~1id"}
    assert next(field for field in candidate["fields"] if field["path"] == "/amount")["type"] == "mixed"
    assert "access_token" not in json.dumps(result)
    assert "private-order-value" not in json.dumps(result)
    assert "private-name" not in json.dumps(result)


def test_only_reports_object_arrays_and_bounds_traversal():
    result = discover_response(json.dumps({"items": [{"id": 1}], "numbers": [1, 2], "empty": []}))
    assert [item["itemsPointer"] for item in result["candidates"]] == ["/items"]


def test_rejects_invalid_or_oversized_json():
    with pytest.raises(ValueError, match="valid JSON"):
        discover_response("not json")
    with pytest.raises(ValueError, match="2 MB"):
        discover_response(" " * 2_000_001)


def test_caps_number_of_candidates():
    body = json.dumps({f"items{i}": [{"id": i}] for i in range(40)})
    assert len(discover_response(body)["candidates"]) <= 20


def test_detects_cursor_and_next_link_hints_without_exposing_response_values():
    body = json.dumps({
        "data": {"items": [{"id": "private-item"}]},
        "meta": {"next_cursor": "private-cursor", "links": {"next": "https://api.example/page?cursor=private"}},
    })

    result = discover_response(body)

    assert {hint["strategy"] for hint in result["paginationHints"]} == {"cursor", "next_link"}
    cursor = next(hint for hint in result["paginationHints"] if hint["strategy"] == "cursor")
    link = next(hint for hint in result["paginationHints"] if hint["strategy"] == "next_link")
    assert cursor["pointer"] == "/meta/next_cursor"
    assert cursor["queryParam"] == "cursor"
    assert link["pointer"] == "/meta/links/next"
    assert all(hint["confidence"] == "heuristic" for hint in result["paginationHints"])
    serialized = json.dumps(result)
    assert "private-item" not in serialized
    assert "private-cursor" not in serialized
    assert "private" not in serialized


def test_pagination_hints_skip_sensitive_properties_and_bound_candidates():
    result = discover_response(json.dumps({
        "next_cursor": "sensitive-cursor",
        "access_token": "must-not-leak",
        "paging": {"next_page_token": "private-page-token"},
        "items": [{"id": 1}],
    }))

    assert {hint["pointer"] for hint in result["paginationHints"]} == {
        "/next_cursor", "/paging/next_page_token",
    }
    assert "must-not-leak" not in json.dumps(result)
    assert "private-page-token" not in json.dumps(result)
