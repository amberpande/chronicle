FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chronicle/backend/ ./chronicle/backend/
COPY chronicle/__init__.py* ./chronicle/ 2>/dev/null || true

EXPOSE 8080

CMD ["uvicorn", "chronicle.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
