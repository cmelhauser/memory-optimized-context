# The base is pinned by digest (the index, so arm64 and amd64 both resolve); the tag says which release that is.
# Dependabot proposes a newer patch, and CI builds it.
FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
# git settings go in /etc/gitconfig, not ~/.gitconfig: Compose sets HOME to the host's path.
# Python packages come from requirements-runtime.txt: exact versions and hashes, pip refuses anything else.
COPY requirements-runtime.txt /tmp/requirements-runtime.txt
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --require-hashes -r /tmp/requirements-runtime.txt && rm /tmp/requirements-runtime.txt \
 && git config --system --add safe.directory '*' \
 && git config --system user.email memory@local && git config --system user.name memory
COPY bin/memory /app/memory
COPY tools/eval_recall.py /app/eval_recall.py
RUN chmod +x /app/memory
ENV MEMORY_DB=/data/memory.db PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8765
ENTRYPOINT ["python3", "/app/memory"]
# The container listens beyond itself; Compose publishes it on the host's loopback only. Nothing may follow the
# array on its line: Docker would no longer read it as JSON and would run it through /bin/sh instead.
CMD ["mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
