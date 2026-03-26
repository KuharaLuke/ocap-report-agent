# OCAP Report Agent

Generates After Action Reports from Arma 3 OCAP2 mission replay data. Supports both local LLMs via [LM Studio](https://lmstudio.ai/) and cloud inference via the Anthropic API (Claude).

## Features

- **Mission Replay Parsing** — Loads OCAP2 `.json.gz` replay files and extracts entities, events, positions, and timeline data
- **LLM-Powered AAR Generation** — Sends structured briefings to a local LLM (LM Studio / OpenAI-compatible) or the Anthropic API to produce formal military After Action Reports
- **Dual LLM Backend** — Auto-selects Anthropic (Claude) when `ANTHROPIC_API_KEY` is set; falls back to LM Studio otherwise. No code changes needed.
- **Configurable AAR Template** — Reports follow an 8-section military AAR format; supply a custom `.docx` template via `--template` to apply your unit's branding
- **DOCX Export** — Converts reports to formatted Word documents with custom header banner, page numbering, and military-style formatting
- **Discord Integration** — Extracts pre-mission intelligence from Discord planning threads to enrich AAR sections; reads image attachments via vision LLM
- **Map Tile Scraper** — Downloads Leaflet map tiles for 64 Arma 3 maps from [Arma3Map](https://jetelain.github.io/Arma3Map/) with multithreaded downloads and resume support
- **VLM Terrain Analyzer** — Uses a Vision Language Model to analyze map tiles and extract geological features, building types, vegetation, and tactical assessments
- **Terrain-Aware Narratives** — Enriches combat reports with grid references, city names, and terrain context
- **AI Agent Skill** — Generate AARs via `/generate-aar` in Claude Code or OpenClaw

## Requirements

- Python 3.11+
- **One of:**
  - [LM Studio](https://lmstudio.ai/) running locally with a text model loaded (Qwen 3.5 9B recommended)
  - An Anthropic API key (`ANTHROPIC_API_KEY`) — no local model required
- **Vision model** (optional): Any LM Studio vision model (e.g. Qwen3-VL-4B) for Discord image OCR and terrain analysis

## Quick Start

```bash
# Clone and setup
git clone https://github.com/KuharaLuke/ocap-report-agent.git
cd ocap-report-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**Option A — Local (LM Studio):** load a text model in LM Studio, then:

```bash
DATA_FILE=./your_mission.json.gz aar-pipeline
```

**Option B — Cloud (Anthropic):**

```bash
ANTHROPIC_API_KEY=sk-ant-... DATA_FILE=./your_mission.json.gz aar-pipeline
```

Output is saved to `test_output/`:
- `combat_report.md` — AAR in Markdown
- `combat_report.docx` — Formatted Word document
- `briefing.txt` — Structured mission data sent to the LLM

## Installation

### From source (recommended)

```bash
pip install -e ".[dev]"
```

### As a dependency

```bash
pip install git+https://github.com/KuharaLuke/ocap-report-agent.git
```

### Docker

```bash
docker compose up
```

### AI Agent Skills (Claude Code / OpenClaw)

The repo ships a `generate-aar` skill and is a Claude Code plugin, compatible with both Claude Code and OpenClaw.

**Claude Code — in-repo use**

When you open this repo in Claude Code the skill is available automatically:

```
/generate-aar path/to/mission.json.gz
```

**Claude Code — plugin install**

Install the repo as a plugin so the skill is available from any project:

```bash
claude plugin install https://github.com/KuharaLuke/ocap-report-agent
```

Then set `AAR_PIPELINE_PATH` to the cloned repo location:

```bash
export AAR_PIPELINE_PATH=/path/to/ocap-report-agent
```

**OpenClaw**

1. Copy the skill to your global skills directory or point OpenClaw at the repo:
   ```bash
   cp -r skills/generate-aar ~/.openclaw/skills/
   ```

2. Set `AAR_PIPELINE_PATH`:
   ```bash
   export AAR_PIPELINE_PATH=/path/to/ocap-report-agent
   ```

3. Set `ANTHROPIC_API_KEY` (OpenClaw uses Claude by default):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

4. Attach your `.json.gz` replay file and invoke `/generate-aar`.

## Configuration

Copy `.env.example` to `.env` and edit:

```env
DATA_FILE=./mission_replay.json.gz

# LLM backend — pick one:
ANTHROPIC_API_KEY=sk-ant-...          # Use Claude (auto-detected when set)
LLM_URL=http://127.0.0.1:1234        # Use LM Studio (default when no API key)

# Optional: custom Anthropic-compatible base URL (proxy / OpenClaw relay)
# ANTHROPIC_BASE_URL=https://api.anthropic.com

# Output
OUTPUT_DIR=./test_output

# Required when using the AI agent skill outside the repo
AAR_PIPELINE_PATH=/path/to/ocap-report-agent

# Optional: Discord integration for pre-mission intel
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_CHANNEL_ID=your_channel_id
DISCORD_GUILD_ID=your_guild_id
```

When `ANTHROPIC_API_KEY` is set, `LLM_URL` is ignored for report generation. The pipeline prints which backend is active at startup.

## Usage

### Generate an After Action Report

```bash
DATA_FILE=./mission.json.gz aar-pipeline

# With a custom unit template
DATA_FILE=./mission.json.gz aar-pipeline --template path/to/template.docx

# Override the LLM endpoint
DATA_FILE=./mission.json.gz aar-pipeline --llm-url http://localhost:1234
```

### Generate Briefing Data Only (no LLM)

```bash
DATA_FILE=./mission.json.gz aar-pipeline --briefing-only
```

Output: `test_output/briefing.txt` — structured mission data you can use to write the AAR manually or feed to any LLM.

### Convert an Existing Report to DOCX

```bash
aar-pipeline --convert-only
```

Reads `test_output/combat_report.md` and produces `test_output/combat_report.docx`. Useful when editing the report by hand.

### Download Map Tiles

```bash
# Download all 64 maps (~90k tiles, ~20-30 min with 8 threads)
python scrape_tiles.py

# Download a single map
python scrape_tiles.py --map tanoa

# Verify download completeness
python scrape_tiles.py --verify
```

### Analyze Map Terrain (requires vision model)

```bash
python tile_analyzer.py --map stratis
```

Results are saved to `map_tiles/{mapname}/terrain_analysis.json` and used automatically on the next pipeline run for that map.

### CLI Mission Summary (no LLM)

```bash
python main.py path/to/mission.json.gz
```

## OCAP2 Integration

The pipeline is pip-installable for embedding in other tools:

```python
from aar_pipeline import MissionLoader, ReportBuilder, ReportGenerator

mission = MissionLoader.load("replay.json.gz")
builder = ReportBuilder(mission)
briefing = builder.build()

# Local LLM (LM Studio)
generator = ReportGenerator(base_url="http://localhost:1234", provider="openai")

# Anthropic (Claude)
generator = ReportGenerator(provider="anthropic", api_key="sk-ant-...")

# Auto-detect from ANTHROPIC_API_KEY env var
generator = ReportGenerator()

report = generator.generate(briefing)
```

## Project Structure

```
ocap-report-agent/
    src/aar_pipeline/        # Core pipeline (pip-installable package)
        models/              # Data models (Entity, Event, Mission, Position)
        cli.py               # Pipeline entry point
        loader.py            # Parses OCAP2 .json.gz replay files
        report_builder.py    # Structures mission data into LLM-ready briefing
        report_generator.py  # Calls LLM with configurable AAR template
        llm_client.py        # Dual-backend LLM client (OpenAI + Anthropic)
        discord_agent.py     # Discord thread intelligence + image OCR
        docx_converter.py    # Markdown to formatted Word conversion
    tests/                   # Unit tests (pytest)
    skills/generate-aar/     # Claude Code / OpenClaw skill
    scrape_tiles.py          # Multithreaded map tile downloader
    tile_analyzer.py         # VLM-based terrain feature extraction
    main.py                  # CLI tool for quick mission summaries
```

## Data Flow

```
OCAP2 .json.gz --> MissionLoader --> Mission object
                                         |
                   terrain + Discord     | (optional)
                                         v
                                    ReportBuilder --> Briefing text
                                                          |
                                                          v
                                    ReportGenerator --> LLM --> AAR (.md)
                                                          |
                                                          v
                                    DocxConverter --> AAR (.docx)
```

## Development

```bash
pytest                # run tests
aar-pipeline          # run the pipeline
python main.py x.gz   # quick summary without LLM
```

## License

MIT
