from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, root_validator

app = FastAPI(title="In-memory TODO API")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


class Todo(BaseModel):
    id: int
    title: str = Field(..., min_length=1, max_length=120)
    done: bool = False


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @root_validator(pre=True)
    def validate_title(cls, values: dict) -> dict:
        title = values.get("title")
        if title is None:
            return values
        stripped = title.strip()
        if not stripped:
            raise ValueError("Title must not be empty")
        values["title"] = stripped
        return values


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


todos: List[Todo] = []
_next_id = 1


def _get_next_id() -> int:
    global _next_id
    next_id = _next_id
    _next_id += 1
    return next_id


def _find_todo_index(todo_id: int) -> int:
    for index, todo in enumerate(todos):
        if todo.id == todo_id:
            return index
    raise HTTPException(status_code=404, detail="TODO not found")


@app.get("/todos", response_model=List[Todo])
def list_todos() -> List[Todo]:
    return todos


@app.post("/todos", response_model=Todo, status_code=201)
def create_todo(payload: TodoCreate) -> Todo:
    todo = Todo(id=_get_next_id(), title=payload.title, done=False)
    todos.append(todo)
    return todo


@app.patch("/todos/{todo_id}", response_model=Todo)
def update_todo(
    payload: TodoUpdate,
    todo_id: int = Path(..., ge=1, description="Identifier of the TODO item"),
) -> Todo:
    index = _find_todo_index(todo_id)
    todo = todos[index]

    update_data = payload.dict(exclude_unset=True)

    if "title" in update_data:
        todo.title = update_data["title"]

    if "done" in update_data:
        todo.done = update_data["done"]

    todos[index] = todo
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int = Path(..., ge=1)) -> None:
    index = _find_todo_index(todo_id)
    todos.pop(index)
