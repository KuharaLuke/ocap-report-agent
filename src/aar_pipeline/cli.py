"""Generate a combat after-action report from OCAP2 mission data via local LLM."""

import argparse
import json
import os
import sys
from pathlib import Path

from .loader import MissionLoader
from .template_config import TemplateConfig


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load key=value pairs from a .env file into os.environ (no overwrite)."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aar-pipeline",
        description="Generate After Action Reports from OCAP2 mission replays",
    )
    parser.add_argument(
        "data_file",
        nargs="?",
        help="Path to OCAP2 mission file (.json.gz). Falls back to DATA_FILE env var.",
    )
    parser.add_argument(
        "-t", "--template",
        help="Path to AAR template .docx file",
    )
    parser.add_argument(
        "--llm-url",
        default=None,
        help="LLM endpoint URL (default: http://127.0.0.1:1234)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Output directory (default: ./test_output)",
    )
    parser.add_argument(
        "--briefing-only",
        action="store_true",
        help="Generate briefing data only, skip LLM report generation",
    )
    parser.add_argument(
        "--convert-only",
        action="store_true",
        help="Convert existing combat_report.md to .docx only (no data processing)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Resolve config: CLI arg > env var > default
    llm_url = args.llm_url or os.environ.get("LLM_URL", "http://127.0.0.1:1234")
    output_dir = Path(args.output_dir or os.environ.get("OUTPUT_DIR", "./test_output"))
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    provider = "anthropic" if api_key else "openai"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load template
    template = None
    if args.template:
        template_path = Path(args.template)
        if not template_path.exists():
            print(f"ERROR: Template not found: {template_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Loading template from {template_path} ...")
        template = TemplateConfig.from_docx(template_path)
        print(f"  Unit: {template.unit_name}, {len(template.sections)} sections")
    else:
        template = TemplateConfig.default()

    # --convert-only: just run docx converter on existing .md
    if args.convert_only:
        from .docx_converter import DocxConverter
        md_path = output_dir / "combat_report.md"
        if not md_path.exists():
            print(f"ERROR: {md_path} not found", file=sys.stderr)
            sys.exit(1)
        report = md_path.read_text(encoding="utf-8")
        docx_path = output_dir / "combat_report.docx"
        converter = DocxConverter(report, template=template)
        converter.save(docx_path)
        print(f"DOCX saved to {docx_path}")
        return

    # Resolve data file
    data_file = args.data_file or os.environ.get("DATA_FILE")
    if not data_file:
        print(
            "ERROR: No data file specified.\n"
            "Usage: aar-pipeline path/to/mission.json.gz\n"
            "   or: DATA_FILE=path/to/mission.json.gz aar-pipeline",
            file=sys.stderr,
        )
        sys.exit(1)

    data_path = Path(data_file)
    if not data_path.exists():
        print(f"ERROR: File not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Load mission
    print(f"Loading {data_path.name} ...")
    mission = MissionLoader.load(data_path)
    print(f"  {len(mission.entities)} entities, {len(mission.kills)} kills, {len(mission.hits)} hits")

    # 1b. Export debug data
    _export_debug_mission(mission, output_dir)

    # 2. Lazy download map data
    from .map_downloader import MapDownloader
    tiles_dir = Path("map_tiles")
    downloader = MapDownloader()
    config_data = downloader.ensure_config(mission.world_name, tiles_dir)
    if config_data:
        downloader.ensure_tiles(mission.world_name, zoom=2, tiles_dir=tiles_dir, config=config_data)

    # 2b. Load terrain data (optional)
    terrain_data = None
    terrain_path = tiles_dir / mission.world_name / "terrain_analysis.json"
    if terrain_path.exists():
        with open(terrain_path, "r", encoding="utf-8") as f:
            terrain_data = json.load(f)
        print(f"  Terrain data loaded from {terrain_path}")
    else:
        print(f"  No terrain data for {mission.world_name} (run tile_analyzer.py to generate)")

    # 2c. Load cities data (optional, from map config)
    cities = None
    config_path = tiles_dir / mission.world_name / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            map_config = json.load(f)
        cities = map_config.get("cities", [])
        if cities:
            print(f"  Loaded {len(cities)} city locations for {mission.world_name}")
    else:
        print(f"  No map config for {mission.world_name}")

    # 2d. Fetch Discord context (optional)
    discord_token = os.environ.get("DISCORD_BOT_TOKEN")
    discord_channel = os.environ.get("DISCORD_CHANNEL_ID")
    discord_guild = os.environ.get("DISCORD_GUILD_ID")

    discord_context = None
    if discord_token and discord_channel and discord_guild:
        from .discord_agent import DiscordAgent
        from .llm_client import LLMClient
        print("Fetching Discord planning context ...")
        llm = LLMClient(base_url=llm_url, provider=provider, api_key=api_key)
        agent = DiscordAgent(
            bot_token=discord_token,
            channel_id=discord_channel,
            guild_id=discord_guild,
            llm_client=llm,
        )
        mission_date = mission.times[0].system_time_utc if mission.times else None
        if mission_date:
            discord_context = agent.fetch_context(mission_date)
            if discord_context:
                discord_path = output_dir / "discord_context.txt"
                discord_path.write_text(discord_context, encoding="utf-8")
                print(f"  Discord context extracted ({len(discord_context)} chars)")
            else:
                print("  No Discord context available")
        else:
            print("  No mission time data for Discord thread matching")
    else:
        print("  Discord integration not configured (set DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, DISCORD_GUILD_ID)")

    # 3. Build briefing
    from .report_builder import ReportBuilder
    print("Building mission briefing ...")
    builder = ReportBuilder(
        mission,
        terrain_data=terrain_data,
        cities=cities,
        discord_context=discord_context,
    )
    briefing = builder.build()

    briefing_path = output_dir / "briefing.txt"
    briefing_path.write_text(briefing, encoding="utf-8")
    print(f"  Briefing saved to {briefing_path} ({len(briefing)} chars)")

    # Stop here if --briefing-only
    if args.briefing_only:
        print("\n--briefing-only: skipping LLM report generation")
        return

    # 4. Generate report via LLM
    from .report_generator import ReportGenerator
    backend = "Anthropic API" if provider == "anthropic" else f"LM Studio at {llm_url}"
    print(f"Sending to {backend} ...")
    generator = ReportGenerator(base_url=llm_url, template=template, provider=provider, api_key=api_key)
    try:
        report = generator.generate(briefing, discord_context=discord_context)
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Save report
    report_path = output_dir / "combat_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved to {report_path}")

    # 6. Convert to DOCX
    from .docx_converter import DocxConverter
    docx_path = output_dir / "combat_report.docx"
    try:
        converter = DocxConverter(report, template=template)
        converter.save(docx_path)
        print(f"  DOCX saved to {docx_path}")
    except Exception as e:
        print(f"  Warning: DOCX conversion failed: {e}", file=sys.stderr)

    print("\n" + "=" * 60)
    print(report.encode("utf-8", errors="replace").decode("utf-8"))


def _export_debug_mission(mission, output_dir: Path) -> None:
    """Export debug JSONs for each data transform step."""
    from .models.event import ConnectionEvent

    players = []
    for p in mission.players:
        players.append({
            "id": p.id, "name": p.name, "group": p.group, "role": p.role,
            "total_shots": p.total_shots, "death_frame": p.death_frame,
        })
    _write_debug(output_dir / "debug_players.json", players)

    disconnect_frames = {
        e.frame for e in mission.events
        if isinstance(e, ConnectionEvent) and e.event_type == "disconnected"
    }

    kills = []
    for k in mission.kills:
        attacker = mission.get_entity(k.attacker_id)
        victim = mission.get_entity(k.victim_id)
        is_self = k.victim_id == k.attacker_id
        weapon = k.weapon.strip() if k.weapon else ""
        weapon_empty = weapon in ("", "[]")

        if is_self and weapon_empty:
            classification = "respawn_artifact"
        elif is_self and k.distance == 0 and k.frame in disconnect_frames:
            classification = "disconnect_artifact"
        elif k.attacker_id == -1 and weapon_empty and k.distance == -1:
            classification = "environmental_death"
        elif is_self:
            classification = "self_kill"
        else:
            classification = "combat_kill"

        kills.append({
            "frame": k.frame,
            "victim_id": k.victim_id,
            "victim_name": victim.name if victim else "?",
            "victim_is_player": victim.is_player if victim else False,
            "attacker_id": k.attacker_id,
            "attacker_name": attacker.name if attacker else "?",
            "weapon": k.weapon,
            "distance": k.distance,
            "classification": classification,
        })
    _write_debug(output_dir / "debug_kills.json", kills)

    stats = {
        "total_entities": len(mission.entities),
        "total_players": len(mission.players),
        "unique_player_names": len(set(p.name for p in mission.players)),
        "total_kills": len(mission.kills),
        "combat_kills": sum(1 for k in kills if k["classification"] == "combat_kill"),
        "self_kills": sum(1 for k in kills if k["classification"] == "self_kill"),
        "respawn_artifacts": sum(1 for k in kills if k["classification"] == "respawn_artifact"),
        "disconnect_artifacts": sum(1 for k in kills if k["classification"] == "disconnect_artifact"),
        "environmental_deaths": sum(1 for k in kills if k["classification"] == "environmental_death"),
        "total_hits": len(mission.hits),
        "player_kia_events": sum(1 for k in kills if k["victim_is_player"]),
    }
    _write_debug(output_dir / "debug_stats.json", stats)
    print(f"  Debug: {stats['combat_kills']} combat, {stats['self_kills']} self, "
          f"{stats['respawn_artifacts']} respawn, {stats['disconnect_artifacts']} disconnect, "
          f"{stats['environmental_deaths']} environmental")


def _write_debug(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
