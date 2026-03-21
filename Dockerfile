FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY AAR_Template/header_banner.png AAR_Template/header_banner.png

RUN pip install --no-cache-dir .

RUN mkdir -p /app/output

ENV LLM_URL=http://host.docker.internal:1234
ENV DATA_FILE=/app/data/mission.json.gz
ENV OUTPUT_DIR=/app/output

CMD ["aar-pipeline"]
