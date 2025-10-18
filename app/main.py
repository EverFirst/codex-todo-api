from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from fastapi import Body, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conlist, root_validator, validator

app = FastAPI(title="In-memory TODO API")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = "; ".join(error.get("msg", "Invalid request") for error in exc.errors())
    return JSONResponse(status_code=400, content=ErrorResponse(detail=details).dict())


class Todo(BaseModel):
    id: int
    title: str = Field(..., min_length=1, max_length=120)
    done: bool = False
    deleted: bool = False


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @validator("title")
    def validate_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title must not be empty")
        if len(stripped) > 120:
            raise ValueError("Title must be at most 120 characters long")
        return stripped


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    done: Optional[bool] = None

    @root_validator(pre=True)
    def validate_payload(cls, values: dict) -> dict:
        if not values:
            raise ValueError("At least one field must be provided for update")

        title = values.get("title")
        if title is not None:
            stripped = title.strip()
            if not stripped:
                raise ValueError("Title must not be empty")
            values["title"] = stripped

        if "title" not in values and "done" not in values:
            raise ValueError("At least one field must be provided for update")

        return values

    @validator("title")
    def validate_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title must not be empty")
        if len(stripped) > 120:
            raise ValueError("Title must be at most 120 characters long")
        return stripped


class TodoListResponse(BaseModel):
    items: List[Todo]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str


class BulkUpdatePayload(BaseModel):
    ids: conlist(int, min_items=1) = Field(..., example=[1, 2, 3])
    done: Optional[bool] = Field(None, example=True)
    title_prefix: Optional[str] = Field(
        None, example="[Updated] "
    )

    @root_validator
    def validate_operation(cls, values: dict) -> dict:
        if values.get("done") is None and values.get("title_prefix") is None:
            raise ValueError("At least one update operation must be provided")
        return values


class BulkDeletePayload(BaseModel):
    ids: conlist(int, min_items=1) = Field(..., example=[1, 2])


class MetricsResponse(BaseModel):
    count_total: int
    count_done: int


class HealthResponse(BaseModel):
    status: str


todos: List[Todo] = []
_next_id = 1


def _get_next_id() -> int:
    global _next_id
    next_id = _next_id
    _next_id += 1
    return next_id


def _find_todo_index(todo_id: int, *, include_deleted: bool = False) -> int:
    for index, todo in enumerate(todos):
        if todo.id == todo_id:
            if todo.deleted and not include_deleted:
                break
            return index
    raise HTTPException(status_code=404, detail="TODO not found")


def _existing_titles(exclude_ids: Optional[Sequence[int]] = None) -> Iterable[str]:
    excluded = set(exclude_ids or [])
    for todo in todos:
        if todo.deleted:
            continue
        if todo.id in excluded:
            continue
        yield todo.title.casefold()


def _ensure_unique_title(title: str, *, exclude_id: Optional[int] = None) -> None:
    normalized = title.casefold()
    existing = set(_existing_titles(exclude_ids=[exclude_id] if exclude_id else None))
    if normalized in existing:
        raise HTTPException(status_code=409, detail="TODO title already exists")


@app.get(
    "/todos",
    response_model=TodoListResponse,
    responses={400: {"model": ErrorResponse}},
)
def list_todos(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort: str = Query("id", regex=r"^-?id$|^title$"),
    query: Optional[str] = Query(None, min_length=1),
    done: Optional[bool] = None,
    include_deleted: bool = False,
) -> TodoListResponse:
    filtered: List[Todo] = []
    search_term = query.strip().casefold() if query else None

    for todo in todos:
        if not include_deleted and todo.deleted:
            continue
        if done is not None and todo.done is not done:
            continue
        if search_term and search_term not in todo.title.casefold():
            continue
        filtered.append(todo)

    if sort == "id":
        filtered.sort(key=lambda item: item.id)
    elif sort == "-id":
        filtered.sort(key=lambda item: item.id, reverse=True)
    elif sort == "title":
        filtered.sort(key=lambda item: (item.title.casefold(), item.id))
    else:
        raise HTTPException(status_code=400, detail="Invalid sort parameter")

    total = len(filtered)
    sliced_items = filtered[offset : offset + limit]

    return TodoListResponse(items=sliced_items, total=total, offset=offset, limit=limit)


@app.post(
    "/todos",
    response_model=Todo,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_todo(payload: TodoCreate) -> Todo:
    _ensure_unique_title(payload.title)
    todo = Todo(id=_get_next_id(), title=payload.title, done=False, deleted=False)
    todos.append(todo)
    return todo


@app.post(
    "/todos/bulk",
    response_model=List[Todo],
    status_code=201,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_todos_bulk(payload: List[TodoCreate] = Body(...)) -> List[Todo]:
    if not payload:
        return []

    normalized_existing = set(_existing_titles())
    new_titles: List[str] = []

    for item in payload:
        normalized = item.title.casefold()
        if normalized in normalized_existing or normalized in new_titles:
            raise HTTPException(status_code=409, detail="TODO title already exists")
        new_titles.append(normalized)

    created: List[Todo] = []
    for item in payload:
        todo = Todo(id=_get_next_id(), title=item.title, done=False, deleted=False)
        todos.append(todo)
        created.append(todo)
    return created


@app.patch(
    "/todos/{todo_id}",
    response_model=Todo,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def update_todo(
    payload: TodoUpdate,
    todo_id: int = Path(..., ge=1, description="Identifier of the TODO item"),
) -> Todo:
    index = _find_todo_index(todo_id)
    todo = todos[index]

    update_data = payload.dict(exclude_unset=True)

    if "title" in update_data:
        new_title = update_data["title"]
        _ensure_unique_title(new_title, exclude_id=todo.id)
        todo.title = new_title

    if "done" in update_data:
        todo.done = update_data["done"]

    todos[index] = todo
    return todo


@app.patch(
    "/todos/bulk",
    response_model=List[Todo],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def bulk_update_todos(payload: BulkUpdatePayload) -> List[Todo]:
    indices = [_find_todo_index(todo_id) for todo_id in payload.ids]

    new_titles: dict[int, str] = {}

    if payload.title_prefix is not None:
        prefix = payload.title_prefix
        for idx in indices:
            todo = todos[idx]
            candidate = f"{prefix}{todo.title}".strip()
            if not candidate:
                raise HTTPException(status_code=400, detail="Title must not be empty")
            if len(candidate) > 120:
                raise HTTPException(
                    status_code=400, detail="Title must be at most 120 characters long"
                )
            new_titles[todo.id] = candidate

        existing = set(_existing_titles(exclude_ids=new_titles.keys()))
        normalized_new = []
        for candidate in new_titles.values():
            normalized = candidate.casefold()
            if normalized in existing:
                raise HTTPException(status_code=409, detail="TODO title already exists")
            normalized_new.append(normalized)
        if len(set(normalized_new)) != len(normalized_new):
            raise HTTPException(status_code=409, detail="TODO title already exists")

    updated: List[Todo] = []
    for idx in indices:
        todo = todos[idx]
        if payload.done is not None:
            todo.done = payload.done
        if payload.title_prefix is not None:
            todo.title = new_titles[todo.id]
        todos[idx] = todo
        updated.append(todo)

    return updated


@app.delete(
    "/todos/bulk",
    status_code=204,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def bulk_delete_todos(payload: BulkDeletePayload = Body(...)) -> None:
    indices = sorted({_find_todo_index(todo_id) for todo_id in payload.ids}, reverse=True)
    for idx in indices:
        todo = todos[idx]
        todo.deleted = True
        todos[idx] = todo


@app.delete(
    "/todos/{todo_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
def delete_todo(todo_id: int = Path(..., ge=1)) -> None:
    index = _find_todo_index(todo_id)
    todo = todos[index]
    todo.deleted = True
    todos[index] = todo


@app.post(
    "/todos/{todo_id}/restore",
    response_model=Todo,
    responses={404: {"model": ErrorResponse}},
)
def restore_todo(todo_id: int = Path(..., ge=1)) -> Todo:
    index = _find_todo_index(todo_id, include_deleted=True)
    todo = todos[index]
    todo.deleted = False
    todos[index] = todo
    return todo


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    active = [todo for todo in todos if not todo.deleted]
    total = len(active)
    done_count = sum(1 for todo in active if todo.done)
    return MetricsResponse(count_total=total, count_done=done_count)
