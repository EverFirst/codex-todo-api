# codex-todo-api

간단한 FastAPI 기반의 인메모리 TODO API 입니다. 애플리케이션은 데이터베이스 없이 프로세스 내 리스트만을 사용하며 서버를 재시작하면 데이터가 초기화됩니다.

## 개발 환경 준비

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행 방법

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger UI는 `http://localhost:8000/docs` 에서 확인할 수 있습니다.

## 테스트

```bash
pytest
```
