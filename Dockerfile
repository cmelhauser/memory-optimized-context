FROM python:3.12.6-slim-bookworm
# git settings go in /etc/gitconfig, not ~/.gitconfig: Compose sets HOME to the host's path.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir anthropic==1.5.0 mcp==2.2.0 numpy==2.4.4 \
 && git config --system --add safe.directory '*' \
 && git config --system user.email memory@local && git config --system user.name memory
COPY bin/memory /app/memory
COPY tools/eval_recall.py /app/eval_recall.py
RUN chmod +x /app/memory
ENV MEMORY_DB=/data/memory.db PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8765
ENTRYPOINT ["python3", "/app/memory"]
CMD ["mcp", "--transport", "http", "--port", "8765"]
