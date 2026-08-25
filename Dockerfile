FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

EXPOSE 8765

CMD ["python3", "-m", "workbench", "--cases-dir", "/data", "serve", "--host", "0.0.0.0"]
