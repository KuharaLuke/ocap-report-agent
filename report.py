"""Generate a combat after-action report from OCAP2 mission data via local LLM."""

import os
import sys
from pathlib import Path

from loader import MissionLoader
from report_builder import ReportBuilder
from report_generator import ReportGenerator


def main() -> None:
    data_file = os.environ.get("DATA_FILE")
    if not data_file:
        print(
            "ERROR: DATA_FILE environment variable is required.\n"
            "Usage: DATA_FILE=path/to/mission.json.gz python report.py",
            file=sys.stderr,
        )
        sys.exit(1)

    data_path = Path(data_file)
    if not data_path.exists():
        print(f"ERROR: File not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    llm_url = os.environ.get("LLM_URL", "http://127.0.0.1:1234")
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./test_output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load mission
    print(f"Loading {data_path.name} ...")
    mission = MissionLoader.load(data_path)
    print(f"  {len(mission.entities)} entities, {len(mission.kills)} kills, {len(mission.hits)} hits")

    # 2. Build briefing
    print("Building mission briefing ...")
    builder = ReportBuilder(mission)
    briefing = builder.build()

    briefing_path = output_dir / "briefing.txt"
    briefing_path.write_text(briefing, encoding="utf-8")
    print(f"  Briefing saved to {briefing_path} ({len(briefing)} chars)")

    # 3. Generate report via LLM
    print(f"Sending to LLM at {llm_url} ...")
    generator = ReportGenerator(base_url=llm_url)
    try:
        report = generator.generate(briefing)
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Save report
    report_path = output_dir / "combat_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved to {report_path}")

    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
