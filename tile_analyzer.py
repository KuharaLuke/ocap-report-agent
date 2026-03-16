"""Analyze map tiles using a Vision Language Model to extract terrain and building features."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

import requests

TILES_DIR = Path(__file__).parent / "map_tiles"

SYSTEM_PROMPT = (
    "You are a military terrain analyst examining topographic map tiles. "
    "Analyze the image and return a JSON object with these fields:\n\n"
    "{\n"
    '  "terrain_type": "coastal" | "mountainous" | "flat" | "hilly" | "forested" | "urban" | "mixed",\n'
    '  "elevation_range": {"min": <number or null>, "max": <number or null>},\n'
    '  "contour_density": "none" | "sparse" | "moderate" | "dense",\n'
    '  "geological_features": [\n'
    '    {"type": "ridgeline" | "valley" | "cliff" | "saddle" | "plateau" | "slope" | "fault_line" | "depression", "description": "<brief>"}\n'
    "  ],\n"
    '  "buildings": [\n'
    '    {"type": "military" | "residential" | "industrial" | "infrastructure" | "religious" | "unknown", "description": "<brief>"}\n'
    "  ],\n"
    '  "roads": {"paved": <count>, "unpaved": <count>},\n'
    '  "vegetation": "none" | "sparse" | "moderate" | "dense",\n'
    '  "water_features": ["sea" | "river" | "lake" | "stream" | "pond"],\n'
    '  "tactical_summary": "<1-2 sentence tactical assessment of terrain>"\n'
    "}\n\n"
    "Return ONLY valid JSON. No explanation or commentary."
)


class TileAnalyzer:
    """Sends map tile images to a VLM via OpenAI-compatible vision API."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        self.url = f"{base_url.rstrip('/')}/v1/chat/completions"

    def analyze_tile(self, image_path: Path) -> dict:
        """Send a single tile image to the VLM and return parsed features."""
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

        payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Analyze this topographic map tile. Return the JSON analysis.",
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        resp = self._post_with_retry(payload)
        content = resp["choices"][0]["message"]["content"]
        return self._parse_response(content)

    def _post_with_retry(self, payload: dict, retries: int = 1) -> dict:
        """POST to VLM with retry on timeout."""
        for attempt in range(retries + 1):
            try:
                resp = requests.post(self.url, json=payload, timeout=120)
                resp.raise_for_status()
                return resp.json()
            except requests.Timeout:
                if attempt < retries:
                    print("    Timeout, retrying...")
                    time.sleep(2)
                    continue
                raise TimeoutError("VLM request timed out after retries.")
            except requests.ConnectionError:
                raise ConnectionError(
                    f"Cannot connect to LM Studio at {self.url}. "
                    "Ensure LM Studio is running with a vision model loaded."
                )
            except requests.HTTPError as e:
                raise RuntimeError(f"VLM API error: {e}")

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Extract JSON from VLM response, handling CoT and markdown fences."""
        # Strip <think>...</think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Strip markdown code fences
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # Try to find JSON object in the text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start : brace_end + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"parse_error": True, "_raw_response": text[:500]}

    def analyze_map(self, map_name: str, zoom: int, tiles_dir: Path) -> dict:
        """Process all tiles at a given zoom level for a map."""
        map_dir = tiles_dir / map_name
        config_path = map_dir / "config.json"

        if not config_path.exists():
            print(f"  No config.json found for {map_name}, skipping")
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        max_zoom = config.get("maxZoom", 5)
        if zoom > max_zoom:
            print(f"  Requested zoom {zoom} exceeds maxZoom {max_zoom}, using {max_zoom}")
            zoom = max_zoom

        grid_size = 2**zoom
        total_tiles = grid_size * grid_size
        tiles_data = {}
        errors = 0

        for x in range(grid_size):
            for y in range(grid_size):
                tile_path = map_dir / str(zoom) / str(x) / f"{y}.png"
                tile_key = f"{x}_{y}"

                if not tile_path.exists():
                    continue

                done = len(tiles_data) + errors + 1
                print(f"\r  Tile {x}/{y} ({done}/{total_tiles})", end="", flush=True)

                try:
                    result = self.analyze_tile(tile_path)
                    tiles_data[tile_key] = result

                    # Print brief summary
                    terrain = result.get("terrain_type", "?")
                    buildings = len(result.get("buildings", []))
                    geo = len(result.get("geological_features", []))
                    err = " [PARSE ERROR]" if result.get("parse_error") else ""
                    print(f"\r  Tile {x}/{y}: {terrain}, {buildings} buildings, {geo} geo features{err}")
                except (TimeoutError, ConnectionError, RuntimeError) as e:
                    print(f"\r  Tile {x}/{y}: ERROR - {e}")
                    tiles_data[tile_key] = {"error": str(e)}
                    errors += 1

                time.sleep(2)

        # Build summary
        summary = self._build_summary(tiles_data)

        return {
            "map_name": map_name,
            "zoom_level": zoom,
            "world_size": config.get("worldSize"),
            "tile_count": len(tiles_data),
            "tiles": tiles_data,
            "summary": summary,
        }

    @staticmethod
    def _build_summary(tiles_data: dict) -> dict:
        """Aggregate tile analyses into a map-level summary."""
        terrain_counts: dict[str, int] = {}
        total_buildings = 0
        total_geo = 0
        has_water = False
        has_urban = False

        for tile in tiles_data.values():
            if tile.get("parse_error") or tile.get("error"):
                continue

            terrain = tile.get("terrain_type", "unknown")
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
            total_buildings += len(tile.get("buildings", []))
            total_geo += len(tile.get("geological_features", []))

            if tile.get("water_features"):
                has_water = True
            if terrain == "urban":
                has_urban = True
            if any(b.get("type") in ("residential", "industrial") for b in tile.get("buildings", [])):
                has_urban = True

        dominant = max(terrain_counts, key=terrain_counts.get) if terrain_counts else "unknown"

        return {
            "dominant_terrain": dominant,
            "terrain_distribution": terrain_counts,
            "has_urban_areas": has_urban,
            "has_water": has_water,
            "building_count": total_buildings,
            "geological_feature_count": total_geo,
        }


def discover_maps(tiles_dir: Path) -> list[str]:
    """Find all maps that have downloaded tiles."""
    maps = []
    if not tiles_dir.exists():
        return maps
    for d in sorted(tiles_dir.iterdir()):
        if d.is_dir() and (d / "config.json").exists():
            maps.append(d.name)
    return maps


def main():
    parser = argparse.ArgumentParser(description="Analyze map tiles with a VLM")
    parser.add_argument("--map", type=str, help="Analyze only this map")
    parser.add_argument("--zoom", type=int, default=2, help="Zoom level to analyze (default: 2)")
    parser.add_argument("--llm-url", type=str, default="http://127.0.0.1:1234", help="LM Studio URL")
    parser.add_argument("--skip-existing", action="store_true", help="Skip maps with existing analysis")
    parser.add_argument("--tiles-dir", type=str, default=str(TILES_DIR), help="Tiles directory")
    args = parser.parse_args()

    tiles_dir = Path(args.tiles_dir)
    analyzer = TileAnalyzer(args.llm_url)

    if args.map:
        maps = [args.map]
    else:
        maps = discover_maps(tiles_dir)
        if not maps:
            print(f"No maps found in {tiles_dir}. Run scrape_tiles.py first.")
            sys.exit(1)

    total_maps = len(maps)
    start_time = time.time()
    analyzed = 0
    skipped = 0

    for i, map_name in enumerate(maps, 1):
        output_path = tiles_dir / map_name / "terrain_analysis.json"

        if args.skip_existing and output_path.exists():
            print(f"[{i}/{total_maps}] {map_name} — skipped (analysis exists)")
            skipped += 1
            continue

        grid = 2 ** args.zoom
        print(f"[{i}/{total_maps}] {map_name} ({grid * grid} tiles at zoom {args.zoom})")

        result = analyzer.analyze_map(map_name, args.zoom, tiles_dir)
        if not result:
            continue

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  Saved to {output_path}")
        analyzed += 1

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print(f"\n{'=' * 40}")
    print(f"COMPLETE in {minutes}m {seconds}s")
    print(f"  Analyzed: {analyzed}")
    print(f"  Skipped:  {skipped}")


if __name__ == "__main__":
    main()
