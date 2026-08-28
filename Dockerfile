FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Fixed uid/gid so the /data volume's ownership is predictable across rebuilds.
RUN groupadd --system --gid 10001 workbench \
 && useradd --system --uid 10001 --gid 10001 --no-create-home workbench

WORKDIR /app
COPY --chown=workbench:workbench . /app

# The case database and attachments live on a mounted volume; create the
# mountpoint owned by the runtime user so the service can write without root.
RUN mkdir -p /data && chown workbench:workbench /data

USER workbench

EXPOSE 8765

CMD ["python3", "-m", "workbench", "--cases-dir", "/data", "serve", "--host", "0.0.0.0"]
