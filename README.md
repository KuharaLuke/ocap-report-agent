# OCAP Report Agent

Generates After Action Reports from Arma 3 OCAP2 mission replay data using local LLMs. Follows the Task Force 405 AAR template with optional terrain-aware narratives powered by Vision Language Models.

## Features

- **Mission Replay Parsing** - Loads OCAP2 `.json.gz` replay files and extracts entities, events, positions, and timeline data
- **LLM-Powered AAR Generation** - Sends structured briefings to a local LLM (via OpenAI-compatible API) to produce formal military After Action Reports
- **TF405 Template** - Reports follow the 8-section TF405 AAR format (General Info, Summary, Narrative, Friendly/Enemy Assessment, Intel, Recommendations, Conclusion)
- **Map Tile Scraper** - Downloads Leaflet map tiles for 64 Arma 3 maps from [Arma3Map](https://jetelain.github.io/Arma3Map/) with multithreaded downloads and resume support
- **VLM Terrain Analyzer** - Uses a Vision Language Model to analyze map tiles and extract geological features, building types, vegetation, and tactical assessments
- **Terrain-Aware Narratives** - Enriches combat reports with grid references and terrain context (e.g., "encountered heavy contact in valley terrain at grid 0512")

## Requirements

- Python 3.12+
- [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible API at `localhost:1234`)
- **Text model**: Qwen 3.5 9B (for report generation)
- **Vision model** (optional): Qwen3-VL-4B (for terrain analysis)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/KuharaLuke/ocap-report-agent.git
cd ocap-report-agent
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt

# Load a text model in LM Studio, then:
DATA_FILE=./your_mission.json.gz python report.py
```

Output is saved to `test_output/combat_report.md`.

## Usage

### Generate an After Action Report

```bash
DATA_FILE=./mission.json.gz python report.py
```

Environment variables:
- `DATA_FILE` (required) - Path to OCAP2 `.json.gz` replay file
- `LLM_URL` (default: `http://127.0.0.1:1234`) - LM Studio endpoint
- `OUTPUT_DIR` (default: `./test_output`) - Output directory

### Download Map Tiles

```bash
# Download all 64 maps (~90k tiles, ~20-30 min with 8 threads)
python scrape_tiles.py

# Download a single map
python scrape_tiles.py --map tanoa

# Verify download completeness
python scrape_tiles.py --verify

# Adjust parallelism
python scrape_tiles.py --workers 16
```

### Analyze Map Terrain (requires VLM)

```bash
# Analyze a single map at zoom level 2 (16 tiles)
python tile_analyzer.py --map stratis

# Analyze all downloaded maps
python tile_analyzer.py --skip-existing
```

Results are saved to `map_tiles/{mapname}/terrain_analysis.json`.

### CLI Mission Summary (no LLM needed)

```bash
python main.py path/to/mission.json.gz
```

## Project Structure

```
ocap-report-agent/
    models/              # Data models (Entity, Event, Mission, Position)
    tests/               # Unit tests (pytest)
    report.py            # Main pipeline: load -> build briefing -> LLM -> AAR
    report_builder.py    # Structures mission data into LLM-ready briefing text
    report_generator.py  # Calls OpenAI-compatible LLM API with template
    loader.py            # Parses OCAP2 .json.gz replay files
    main.py              # CLI tool for quick mission summaries
    scrape_tiles.py      # Multithreaded map tile downloader
    tile_analyzer.py     # VLM-based terrain feature extraction
    Dockerfile           # Container image for report generation
    docker-compose.yml   # Docker Compose config
```

## Docker

```bash
docker compose up
```

Maps the mission file and output directory as volumes. Connects to LM Studio on the host via `host.docker.internal:1234`.

## Data Flow

```
OCAP2 .json.gz ──> MissionLoader ──> Mission object
                                         │
                    terrain_analysis.json │ (optional)
                                         ▼
                                    ReportBuilder ──> Briefing text
                                                         │
                                                         ▼
                                                    ReportGenerator ──> LLM ──> AAR
```
