FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api apps/api
COPY packages packages
COPY infrastructure/migrations infrastructure/migrations
COPY alembic.ini .
COPY infrastructure/vps/api-entrypoint.py /app/preview-entrypoint.py
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/app/preview-entrypoint.py"]
