# Project Conventions

## Setup
- Python 3.12+, virtual env at `.venv/`
- Activate: `.venv/Scripts/activate` (Windows)
- Install: `pip install -e ".[dev]"`

## Running
- Pipeline: `DATA_FILE=./mission.json.gz aar-pipeline`
- Tests: `pytest`
- Quick summary (no LLM): `python main.py mission.json.gz`

## Requirements
- LM Studio running at `http://127.0.0.1:1234` with `qwen/qwen3.5-9b` loaded
- OCAP2 `.json.gz` replay file

## Environment Variables
- `DATA_FILE` (required) - path to OCAP2 replay file
- `LLM_URL` (optional, default: `http://127.0.0.1:1234`)
- `OUTPUT_DIR` (optional, default: `./test_output`)
- `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `DISCORD_GUILD_ID` (all optional)

## Architecture
- Source: `src/aar_pipeline/` (pip-installable package)
- Models: `src/aar_pipeline/models/` (dataclasses for OCAP2 data)
- Entry point: `src/aar_pipeline/cli.py` -> `main()`
- Tests: `tests/` (pytest, uses real `.json.gz` fixture)

## Pipeline Flow
```
OCAP2 .json.gz -> MissionLoader -> Mission object
                                     |
                  terrain_analysis + Discord context (optional)
                                     v
                              ReportBuilder -> briefing text
                                     v
                            ReportGenerator -> LLM -> combat_report.md
                                     v
                            DocxConverter -> combat_report.docx
```
