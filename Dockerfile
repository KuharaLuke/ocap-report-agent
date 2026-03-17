FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY models/ models/
COPY AAR_Template/header_banner.png AAR_Template/header_banner.png
COPY loader.py report_builder.py report_generator.py report.py llm_client.py discord_agent.py docx_converter.py ./

RUN mkdir -p /app/output

ENV LLM_URL=http://host.docker.internal:1234
ENV DATA_FILE=/app/data/mission.json.gz
ENV OUTPUT_DIR=/app/output

CMD ["python", "report.py"]
