FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api apps/api
COPY packages packages
COPY infrastructure/migrations infrastructure/migrations
COPY alembic.ini .
CMD ["sh", "-c", "alembic upgrade head && python -m apps.api.publishing.bootstrap && uvicorn apps.api.publishing.main:app --host 0.0.0.0 --port 8100"]
