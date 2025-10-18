from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def setup_function() -> None:
    main.todos.clear()
    main._next_id = 1


def test_create_and_list_todos() -> None:
    response = client.post("/todos", json={"title": "  청소  "})
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": 1, "title": "청소", "done": False, "deleted": False}

    list_response = client.get("/todos")
    assert list_response.status_code == 200
    assert list_response.json() == {
        "items": [body],
        "total": 1,
        "offset": 0,
        "limit": 100,
    }


def test_list_filters_and_sorting() -> None:
    client.post("/todos", json={"title": "alpha"})
    client.post("/todos", json={"title": "bravo"})
    client.post("/todos", json={"title": "charlie"})

    client.patch("/todos/2", json={"done": True})

    response = client.get("/todos", params={"done": True})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [2]

    response = client.get("/todos", params={"query": "ha", "sort": "title"})
    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["charlie"]

    response = client.get("/todos", params={"sort": "-id", "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["id"] == 3
    assert body["total"] == 3
    assert body["limit"] == 1


def test_update_and_conflict_detection() -> None:
    client.post("/todos", json={"title": "alpha"})
    client.post("/todos", json={"title": "bravo"})

    response = client.patch("/todos/1", json={"title": "alpha updated"})
    assert response.status_code == 200
    assert response.json()["title"] == "alpha updated"

    conflict = client.patch("/todos/1", json={"title": "bravo"})
    assert conflict.status_code == 409


def test_soft_delete_and_restore() -> None:
    client.post("/todos", json={"title": "alpha"})

    delete_response = client.delete("/todos/1")
    assert delete_response.status_code == 204

    active = client.get("/todos")
    assert active.json()["items"] == []

    deleted = client.get("/todos", params={"include_deleted": True})
    assert deleted.json()["items"][0]["deleted"] is True

    restore = client.post("/todos/1/restore")
    assert restore.status_code == 200
    assert restore.json()["deleted"] is False


def test_bulk_create_update_and_delete() -> None:
    bulk_create = client.post(
        "/todos/bulk",
        json=[{"title": "alpha"}, {"title": "bravo"}],
    )
    assert bulk_create.status_code == 201
    created = bulk_create.json()
    assert len(created) == 2
    assert created[0]["id"] == 1
    assert created[1]["id"] == 2

    duplicate_bulk = client.post(
        "/todos/bulk",
        json=[{"title": "alpha"}],
    )
    assert duplicate_bulk.status_code == 409

    bulk_update = client.patch(
        "/todos/bulk",
        json={"ids": [1, 2], "done": True, "title_prefix": "[Done] "},
    )
    assert bulk_update.status_code == 200
    assert all(item["done"] for item in bulk_update.json())
    assert all(item["title"].startswith("[Done]") for item in bulk_update.json())

    bulk_delete = client.delete("/todos/bulk", json={"ids": [1, 2]})
    assert bulk_delete.status_code == 204

    deleted = client.get("/todos", params={"include_deleted": True})
    assert all(item["deleted"] for item in deleted.json()["items"])


def test_bulk_update_validation_errors() -> None:
    client.post("/todos", json={"title": "alpha"})

    empty_ops = client.patch("/todos/bulk", json={"ids": [1]})
    assert empty_ops.status_code == 400

    too_long_prefix = "x" * 116
    too_long = client.patch(
        "/todos/bulk",
        json={"ids": [1], "title_prefix": too_long_prefix},
    )
    assert too_long.status_code == 400


def test_metrics_and_health() -> None:
    client.post("/todos", json={"title": "alpha"})
    client.post("/todos", json={"title": "bravo"})
    client.patch("/todos/2", json={"done": True})
    client.delete("/todos/1")

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.json() == {"count_total": 1, "count_done": 1}

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_validation_and_not_found() -> None:
    invalid = client.post("/todos", json={"title": "  "})
    assert invalid.status_code == 400

    missing = client.patch("/todos/999", json={"done": True})
    assert missing.status_code == 404
