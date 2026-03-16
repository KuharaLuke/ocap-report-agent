"""Download all Arma 3 map tiles and metadata from jetelain.github.io/Arma3Map."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://jetelain.github.io/Arma3Map"
OUTPUT_DIR = Path(__file__).parent / "map_tiles"
REQUEST_DELAY = 0.1
CONFIG_DELAY = 0.5
TIMEOUT = 15

MAP_NAMES = [
    "abramia", "altis", "beketov", "blud_vidda", "cam_lao_nam",
    "chernarus", "chernarus_a3s", "chongo", "clafghan", "cup_chernarus_a3",
    "deniland", "dingor", "dya", "eden", "enoch",
    "esseker", "fata", "gm_weferlingen", "gulfcoast", "hellanmaa",
    "hindukush", "isladuala3", "kapaulio", "kerama", "khoramshahr",
    "kujari", "kunduz", "lingor3", "lythium", "malden",
    "mcn_aliabad", "mcn_hazarkot", "mountains_acr", "napf", "napfwinter",
    "northtakistan", "oski_corran", "pabst_yellowstone", "panthera3", "pja305",
    "pja307", "pja310", "pja314", "pja319", "pulau",
    "rhspkl", "rof_mok", "ruha", "sangin_distirict_helmand_province",
    "sara", "sara_dbe1", "seangola", "sefrouramal", "stratis",
    "takistan", "tanoa", "taunus", "tem_anizay", "tem_suursaariv",
    "uzbin", "vt5", "vt7", "wl_rosche", "woodland_acr", "zargabad",
]


def parse_map_config(js_text: str, map_name: str) -> dict:
    """Parse a non-standard JS config file into a Python dict."""
    text = js_text.strip()
    # Strip BOM
    if text.startswith("\ufeff"):
        text = text[1:]

    # Remove wrapper: Arma3Map.Maps.xxx = { ... };
    text = re.sub(r"^Arma3Map\.Maps\.\w+\s*=\s*\{", "{", text)
    text = re.sub(r"\}\s*;\s*$", "}", text)

    # Extract CRS line: CRS: MGRS_CRS(a, b, c)
    crs_data = {}
    crs_match = re.search(r"MGRS_CRS\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*(\d+)\s*\)", text)
    if crs_match:
        crs_data = {
            "scaleX": float(crs_match.group(1)),
            "scaleY": float(crs_match.group(2)),
            "offset": int(crs_match.group(3)),
        }
    # Remove the CRS line entirely
    text = re.sub(r"\"?CRS\"?\s*:\s*MGRS_CRS\([^)]*\)\s*,?", "", text)

    # Quote bare JS keys: word: -> "word":
    text = re.sub(r"(?m)(?<=[\{,\n])\s*(\w+)\s*:", r' "\1":', text)

    # Convert single-quoted strings to double-quoted
    # Match 'value' that's not inside double quotes already
    text = re.sub(r"'([^']*)'", r'"\1"', text)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Clean up any double-comma or empty entries
    text = re.sub(r",\s*,", ",", text)

    try:
        config = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Failed to parse config for {map_name}: {e}")
        print(f"  Preprocessed text (first 500 chars): {text[:500]}")
        return {}

    config["CRS"] = crs_data
    return config


def download_config(session: requests.Session, map_name: str, output_dir: Path) -> dict | None:
    """Download and parse a map's JS config, saving as config.json."""
    map_dir = output_dir / map_name
    config_path = map_dir / "config.json"

    # Resume: if config already exists, load it
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = f"{BASE_URL}/maps/{map_name}.js"
    try:
        resp = session.get(url, timeout=TIMEOUT)
        if resp.status_code == 404:
            print(f"  Config not found (404): {url}")
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching config: {e}")
        return None

    config = parse_map_config(resp.text, map_name)
    if not config:
        return None

    map_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return config


def download_tiles(
    session: requests.Session, map_name: str, config: dict, output_dir: Path, delay: float
) -> tuple[int, int, int]:
    """Download all tiles for a map. Returns (downloaded, skipped, failed)."""
    max_zoom = config.get("maxZoom", 5)
    downloaded = 0
    skipped = 0
    failed = 0

    for z in range(0, max_zoom + 1):
        grid_size = 2**z
        total_tiles = grid_size * grid_size
        z_downloaded = 0
        z_skipped = 0
        z_failed = 0

        for x in range(grid_size):
            for y in range(grid_size):
                tile_path = output_dir / map_name / str(z) / str(x) / f"{y}.png"

                if tile_path.exists() and tile_path.stat().st_size > 0:
                    z_skipped += 1
                    continue

                url = f"{BASE_URL}/maps/{map_name}/{z}/{x}/{y}.png"
                try:
                    resp = session.get(url, timeout=TIMEOUT)
                    if resp.status_code == 200:
                        tile_path.parent.mkdir(parents=True, exist_ok=True)
                        tile_path.write_bytes(resp.content)
                        z_downloaded += 1
                    elif resp.status_code == 404:
                        z_failed += 1
                    else:
                        print(f"  HTTP {resp.status_code} for {url}")
                        z_failed += 1
                except requests.RequestException as e:
                    print(f"  ERROR: {e}")
                    z_failed += 1

                time.sleep(delay)

                # Progress update
                done = z_downloaded + z_skipped + z_failed
                print(f"\r  zoom {z}: {done}/{total_tiles}", end="", flush=True)

        downloaded += z_downloaded
        skipped += z_skipped
        failed += z_failed
        print(f"\r  zoom {z}: {total_tiles} tiles ({z_downloaded} new, {z_skipped} cached, {z_failed} failed)")

    return downloaded, skipped, failed


def calc_total_tiles(max_zoom: int) -> int:
    return sum(4**z for z in range(max_zoom + 1))


def main():
    parser = argparse.ArgumentParser(description="Download Arma 3 map tiles from Arma3Map")
    parser.add_argument("--map", type=str, help="Download only this map")
    parser.add_argument("--dry-run", action="store_true", help="Download configs only, skip tiles")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between tile requests (seconds)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    maps_to_download = [args.map] if args.map else MAP_NAMES
    total_maps = len(maps_to_download)

    session = requests.Session()
    session.headers["User-Agent"] = "Arma3MissionReport-TileScraper/1.0"

    totals = {"downloaded": 0, "skipped": 0, "failed": 0, "config_errors": 0}
    start_time = time.time()

    for i, map_name in enumerate(maps_to_download, 1):
        config = download_config(session, map_name, output_dir)
        if config is None:
            totals["config_errors"] += 1
            print(f"[{i}/{total_maps}] {map_name} — SKIPPED (no config)")
            continue

        max_zoom = config.get("maxZoom", 5)
        tile_count = calc_total_tiles(max_zoom)
        world_size = config.get("worldSize", "?")
        print(f"[{i}/{total_maps}] {map_name} (maxZoom={max_zoom}, ~{tile_count} tiles, world={world_size}m)")

        if args.dry_run:
            continue

        time.sleep(CONFIG_DELAY)

        dl, sk, fl = download_tiles(session, map_name, config, output_dir, args.delay)
        totals["downloaded"] += dl
        totals["skipped"] += sk
        totals["failed"] += fl

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print(f"\n{'=' * 40}")
    print(f"COMPLETE in {minutes}m {seconds}s")
    print(f"  Downloaded:    {totals['downloaded']}")
    print(f"  Cached/skip:   {totals['skipped']}")
    print(f"  Failed (404):  {totals['failed']}")
    print(f"  Config errors: {totals['config_errors']}")


if __name__ == "__main__":
    main()
