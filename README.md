# OCAP Report Agent

Generates After Action Reports from Arma 3 OCAP2 mission replay data using local LLMs. Follows the Task Force 405 AAR template with optional terrain-aware narratives powered by Vision Language Models.

## Features

- **Mission Replay Parsing** - Loads OCAP2 `.json.gz` replay files and extracts entities, events, positions, and timeline data
- **LLM-Powered AAR Generation** - Sends structured briefings to a local LLM (via OpenAI-compatible API) to produce formal military After Action Reports
- **TF405 Template** - Reports follow the 8-section TF405 AAR format (General Info, Summary, Narrative, Friendly/Enemy Assessment, Intel, Recommendations, Conclusion)
- **DOCX Export** - Converts reports to formatted Word documents with TF405 header banner, page numbering, and military-style formatting
- **Discord Integration** - Extracts pre-mission intelligence from Discord planning threads to enrich AAR sections
- **Map Tile Scraper** - Downloads Leaflet map tiles for 64 Arma 3 maps from [Arma3Map](https://jetelain.github.io/Arma3Map/) with multithreaded downloads and resume support
- **VLM Terrain Analyzer** - Uses a Vision Language Model to analyze map tiles and extract geological features, building types, vegetation, and tactical assessments
- **Terrain-Aware Narratives** - Enriches combat reports with grid references, city names, and terrain context

## Requirements

- Python 3.11+
- [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible API at `localhost:1234`)
- **Text model**: Qwen 3.5 9B (for report generation)
- **Vision model** (optional): Qwen3-VL-4B (for terrain analysis)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/KuharaLuke/ocap-report-agent.git
cd ocap-report-agent
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Load a text model in LM Studio, then:
DATA_FILE=./your_mission.json.gz aar-pipeline
```

Output is saved to `test_output/`:
- `combat_report.md` - AAR in Markdown
- `combat_report.docx` - Formatted Word document
- `briefing.txt` - Structured mission data

## Installation

### From source (recommended)

```bash
pip install -e ".[dev]"
```

### As a dependency (for OCAP2 integration)

```bash
pip install git+https://github.com/KuharaLuke/ocap-report-agent.git
```

### Docker

```bash
docker compose up
```

### Claude Code Skill

If you use [Claude Code](https://claude.ai/code), the repo includes a skill:

```
/generate-aar path/to/mission.json.gz
```

## Configuration

Copy `.env.example` to `.env` and edit:

```env
DATA_FILE=./mission_replay.json.gz

# Optional
LLM_URL=http://127.0.0.1:1234
OUTPUT_DIR=./test_output

# Optional: Discord integration for pre-mission intel
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_CHANNEL_ID=your_channel_id
DISCORD_GUILD_ID=your_guild_id
```

## Usage

### Generate an After Action Report

```bash
DATA_FILE=./mission.json.gz aar-pipeline
```

### Download Map Tiles

```bash
# Download all 64 maps (~90k tiles, ~20-30 min with 8 threads)
python scrape_tiles.py

# Download a single map
python scrape_tiles.py --map tanoa

# Verify download completeness
python scrape_tiles.py --verify
```

### Analyze Map Terrain (requires VLM)

```bash
python tile_analyzer.py --map stratis
```

Results are saved to `map_tiles/{mapname}/terrain_analysis.json`.

### CLI Mission Summary (no LLM needed)

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

generator = ReportGenerator(base_url="http://localhost:1234")
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
        report_generator.py  # Calls LLM API with TF405 template
        llm_client.py        # Shared LLM HTTP client
        discord_agent.py     # Discord thread intelligence extraction
        docx_converter.py    # Markdown to formatted Word conversion
    tests/                   # Unit tests (pytest)
    .claude/skills/          # Claude Code skill definitions
    scrape_tiles.py          # Multithreaded map tile downloader
    tile_analyzer.py         # VLM-based terrain feature extraction
    main.py                  # CLI tool for quick mission summaries
```

## Data Flow

```
OCAP2 .json.gz --> MissionLoader --> Mission object
                                        |
                   terrain + Discord    | (optional)
                                        v
                                   ReportBuilder --> Briefing text
                                                        |
                                                        v
                                   ReportGenerator --> LLM --> AAR
                                                        |
                                                        v
                                   DocxConverter --> .docx
```

## Development

```bash
pytest              # run tests
aar-pipeline        # run the pipeline
python main.py x.gz # quick summary without LLM
```

## License

MIT
