"""On-demand map config and tile downloader from Arma3Map."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests


class MapDownloader:
    """Downloads map config and tiles on-demand from jetelain.github.io/Arma3Map."""

    BASE_URL = "https://jetelain.github.io/Arma3Map"
    TIMEOUT = 15

    def ensure_config(self, world_name: str, tiles_dir: Path) -> dict | None:
        """Download and parse config.json if not cached locally.

        Returns the parsed config dict or None on failure.
        """
        map_dir = tiles_dir / world_name
        config_path = map_dir / "config.json"

        # Use cached version if available
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Download the JS config file
        url = f"{self.BASE_URL}/maps/{world_name}.js"
        print(f"  Downloading map config for {world_name}...")
        try:
            resp = requests.get(url, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                print(f"  Map config not found (404): {world_name}")
                return None
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Failed to download map config: {e}")
            return None

        config = self._parse_map_config(resp.text, world_name)
        if not config:
            return None

        # Cache locally
        map_dir.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"  Map config saved to {config_path}")
        return config

    def ensure_tiles(
        self, world_name: str, zoom: int, tiles_dir: Path, config: dict
    ) -> bool:
        """Download tiles at a specific zoom level if missing.

        Only downloads tiles that don't already exist locally.
        Returns True if all tiles are available.
        """
        grid_size = 2**zoom
        map_dir = tiles_dir / world_name
        needed = []

        for x in range(grid_size):
            for y in range(grid_size):
                tile_path = map_dir / str(zoom) / str(x) / f"{y}.png"
                if not tile_path.exists() or tile_path.stat().st_size == 0:
                    needed.append((x, y, tile_path))

        if not needed:
            return True

        print(f"  Downloading {len(needed)} tiles for {world_name} at zoom {zoom}...")
        downloaded = 0
        for x, y, tile_path in needed:
            url = f"{self.BASE_URL}/maps/{world_name}/{zoom}/{x}/{y}.png"
            try:
                resp = requests.get(url, timeout=self.TIMEOUT)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                tile_path.write_bytes(resp.content)
                downloaded += 1
            except requests.RequestException:
                continue

        print(f"  Downloaded {downloaded}/{len(needed)} tiles")
        return downloaded == len(needed)

    @staticmethod
    def _parse_map_config(js_text: str, map_name: str) -> dict:
        """Parse a non-standard JS config file into a Python dict.

        Ported from scrape_tiles.py parse_map_config().
        """
        text = js_text.strip()
        if text.startswith("\ufeff"):
            text = text[1:]

        # Strip JS wrapper
        text = re.sub(r"^Arma3Map\.Maps\.\w+\s*=\s*\{", "{", text)
        text = re.sub(r"\}\s*;\s*$", "}", text)

        # Extract CRS data before removing it
        crs_data = {}
        crs_match = re.search(
            r"MGRS_CRS\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*(\d+)\s*\)", text
        )
        if crs_match:
            crs_data = {
                "scaleX": float(crs_match.group(1)),
                "scaleY": float(crs_match.group(2)),
                "offset": int(crs_match.group(3)),
            }
        text = re.sub(r"\"?CRS\"?\s*:\s*MGRS_CRS\([^)]*\)\s*,?", "", text)

        # Convert JS object to valid JSON
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
