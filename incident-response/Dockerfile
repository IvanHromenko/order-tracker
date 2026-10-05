FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
RUN /opt/venv/bin/pip install --no-cache-dir fastapi uvicorn
RUN npm install --global --no-audit --no-fund @github/copilot

ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /app
COPY incident-response/incident_response ./incident_response
RUN mkdir -p /data /workspace \
    && chown -R node:node /app /data /workspace

USER node
ENV INCIDENT_DB_PATH=/data/incidents.sqlite3 \
    REPOSITORY_ROOT=/workspace
EXPOSE 8001
CMD ["uvicorn", "incident_response.main:app", "--host", "0.0.0.0", "--port", "8001"]