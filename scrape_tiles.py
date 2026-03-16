"""Download all Arma 3 map tiles and metadata from jetelain.github.io/Arma3Map."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE_URL = "https://jetelain.github.io/Arma3Map"
OUTPUT_DIR = Path(__file__).parent / "map_tiles"
TIMEOUT = 15
DEFAULT_WORKERS = 8

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

# Global shutdown event for graceful Ctrl+C
_shutdown = threading.Event()

# Thread-local storage for per-thread requests sessions
_thread_local = threading.local()


def _get_session() -> requests.Session:
    """Get or create a thread-local requests session."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
        _thread_local.session.headers["User-Agent"] = "Arma3MissionReport-TileScraper/2.0"
    return _thread_local.session


def parse_map_config(js_text: str, map_name: str) -> dict:
    """Parse a non-standard JS config file into a Python dict."""
    text = js_text.strip()
    if text.startswith("\ufeff"):
        text = text[1:]

    text = re.sub(r"^Arma3Map\.Maps\.\w+\s*=\s*\{", "{", text)
    text = re.sub(r"\}\s*;\s*$", "}", text)

    crs_data = {}
    crs_match = re.search(r"MGRS_CRS\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*(\d+)\s*\)", text)
    if crs_match:
        crs_data = {
            "scaleX": float(crs_match.group(1)),
            "scaleY": float(crs_match.group(2)),
            "offset": int(crs_match.group(3)),
        }
    text = re.sub(r"\"?CRS\"?\s*:\s*MGRS_CRS\([^)]*\)\s*,?", "", text)

    text = re.sub(r"(?m)(?<=[\{,\n])\s*(\w+)\s*:", r' "\1":', text)
    text = re.sub(r"'([^']*)'", r'"\1"', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)

    try:
        config = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Failed to parse config for {map_name}: {e}")
        return {}

    config["CRS"] = crs_data
    return config


def download_config(map_name: str, output_dir: Path) -> dict | None:
    """Download and parse a map's JS config, saving as config.json."""
    map_dir = output_dir / map_name
    config_path = map_dir / "config.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    session = _get_session()
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


def _download_single_tile(map_name: str, z: int, x: int, y: int, output_dir: Path) -> str:
    """Download a single tile. Returns 'downloaded', 'skipped', or 'failed'."""
    if _shutdown.is_set():
        return "failed"

    tile_path = output_dir / map_name / str(z) / str(x) / f"{y}.png"

    if tile_path.exists() and tile_path.stat().st_size > 0:
        return "skipped"

    session = _get_session()
    url = f"{BASE_URL}/maps/{map_name}/{z}/{x}/{y}.png"
    try:
        resp = session.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = tile_path.with_suffix(".png.tmp")
            tmp_path.write_bytes(resp.content)
            os.replace(str(tmp_path), str(tile_path))
            return "downloaded"
        elif resp.status_code == 404:
            return "failed"
        else:
            return "failed"
    except requests.RequestException:
        return "failed"


def download_tiles(
    map_name: str, config: dict, output_dir: Path, workers: int
) -> tuple[int, int, int]:
    """Download all tiles for a map using a thread pool. Returns (downloaded, skipped, failed)."""
    max_zoom = config.get("maxZoom", 5)
    total_expected = calc_total_tiles(max_zoom)

    # Build list of all tile coordinates
    tasks = []
    for z in range(0, max_zoom + 1):
        grid_size = 2**z
        for x in range(grid_size):
            for y in range(grid_size):
                tasks.append((z, x, y))

    downloaded = 0
    skipped = 0
    failed = 0
    lock = threading.Lock()

    def update_and_report(result: str):
        nonlocal downloaded, skipped, failed
        with lock:
            if result == "downloaded":
                downloaded += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1
            done = downloaded + skipped + failed
            print(f"\r  {done}/{total_expected} tiles ({downloaded} new, {skipped} cached, {failed} failed)", end="", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_download_single_tile, map_name, z, x, y, output_dir): (z, x, y)
            for z, x, y in tasks
        }
        try:
            for future in as_completed(futures):
                if _shutdown.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                update_and_report(future.result())
        except KeyboardInterrupt:
            _shutdown.set()
            executor.shutdown(wait=False, cancel_futures=True)

    print()  # newline after \r progress
    return downloaded, skipped, failed


def calc_total_tiles(max_zoom: int) -> int:
    return sum(4**z for z in range(max_zoom + 1))


def verify_maps(output_dir: Path, map_filter: str | None = None) -> bool:
    """Verify completeness of downloaded tiles. Returns True if all complete."""
    all_ok = True
    maps_checked = 0

    for map_dir in sorted(output_dir.iterdir()):
        if not map_dir.is_dir():
            continue
        config_path = map_dir / "config.json"
        if not config_path.exists():
            continue

        map_name = map_dir.name
        if map_filter and map_name != map_filter:
            continue

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        max_zoom = config.get("maxZoom", 5)
        expected = calc_total_tiles(max_zoom)
        present = 0
        empty = 0
        missing_examples = []

        for z in range(0, max_zoom + 1):
            grid_size = 2**z
            for x in range(grid_size):
                for y in range(grid_size):
                    tile_path = map_dir / str(z) / str(x) / f"{y}.png"
                    if tile_path.exists():
                        if tile_path.stat().st_size > 0:
                            present += 1
                        else:
                            empty += 1
                            if len(missing_examples) < 3:
                                missing_examples.append(f"{z}/{x}/{y}.png (empty)")
                    else:
                        if len(missing_examples) < 3:
                            missing_examples.append(f"{z}/{x}/{y}.png")

        missing = expected - present
        maps_checked += 1

        if missing == 0 and empty == 0:
            print(f"  {map_name}: {present}/{expected} tiles OK")
        else:
            all_ok = False
            parts = []
            if missing > 0:
                parts.append(f"{missing} missing")
            if empty > 0:
                parts.append(f"{empty} empty")
            print(f"  {map_name}: {present}/{expected} tiles ({', '.join(parts)})")
            for ex in missing_examples:
                print(f"    - {ex}")

    if maps_checked == 0:
        print("  No maps found to verify.")
        return False

    print(f"\n  Checked {maps_checked} maps: {'ALL COMPLETE' if all_ok else 'SOME INCOMPLETE'}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Download Arma 3 map tiles from Arma3Map")
    parser.add_argument("--map", type=str, help="Download only this map")
    parser.add_argument("--dry-run", action="store_true", help="Download configs only, skip tiles")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel download threads (default: 8)")
    parser.add_argument("--verify", action="store_true", help="Verify tile completeness, no downloads")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.verify:
        print("Verifying tile completeness...")
        ok = verify_maps(output_dir, args.map)
        sys.exit(0 if ok else 1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\nInterrupted! Finishing current downloads...")
        _shutdown.set()

    signal.signal(signal.SIGINT, signal_handler)

    maps_to_download = [args.map] if args.map else MAP_NAMES
    total_maps = len(maps_to_download)

    totals = {"downloaded": 0, "skipped": 0, "failed": 0, "config_errors": 0}
    start_time = time.time()

    for i, map_name in enumerate(maps_to_download, 1):
        if _shutdown.is_set():
            print("Shutdown requested, stopping.")
            break

        config = download_config(map_name, output_dir)
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

        dl, sk, fl = download_tiles(map_name, config, output_dir, args.workers)
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
