from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def setup_function() -> None:
    main.todos.clear()
    main._next_id = 1


def test_create_and_list_todos():
    response = client.post("/todos", json={"title": "청소"})
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": 1, "title": "청소", "done": False}

    list_response = client.get("/todos")
    assert list_response.status_code == 200
    assert list_response.json() == [body]


def test_update_todo_done_status():
    client.post("/todos", json={"title": "청소"})
    response = client.patch("/todos/1", json={"done": True})
    assert response.status_code == 200
    assert response.json()["done"] is True

    response = client.patch("/todos/1", json={"done": False})
    assert response.status_code == 200
    assert response.json()["done"] is False


def test_delete_todo():
    client.post("/todos", json={"title": "청소"})
    delete_response = client.delete("/todos/1")
    assert delete_response.status_code == 204

    list_response = client.get("/todos")
    assert list_response.json() == []
