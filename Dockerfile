FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Fixed uid/gid so the /data volume's ownership is predictable across rebuilds.
RUN groupadd --system --gid 10001 workbench \
 && useradd --system --uid 10001 --gid 10001 --no-create-home workbench

WORKDIR /app
COPY --chown=workbench:workbench . /app

RUN mkdir -p /data && chown workbench:workbench /data

# The service never runs as root: the entrypoint starts privileged only long
# enough to hand the mounted volume to the workbench user, then drops to it and
# execs CMD. USER is deliberately not set — a volume is mounted over /data after
# the build, so the chown above cannot reach it, and an upgrade from an earlier
# root-running image leaves a database, attachments and backups at mode 0600
# owned by root that an unprivileged process could not open at all.
ENTRYPOINT ["python3", "/app/docker-entrypoint.py"]

EXPOSE 8765

CMD ["python3", "-m", "workbench", "--cases-dir", "/data", "serve", "--host", "0.0.0.0"]
