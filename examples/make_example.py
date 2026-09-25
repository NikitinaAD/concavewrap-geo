from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


def main() -> None:
    destination = Path(__file__).with_name("forest-patches.gpkg")
    patches = gpd.GeoDataFrame(
        {
            "patch_id": ["west", "north", "east", "south-west"],
            "stand": ["demo"] * 4,
        },
        geometry=[
            box(0, 0, 3, 8),
            box(3, 6, 10, 8),
            box(8, 3, 10, 6),
            box(3, 0, 6, 2),
        ],
        crs="EPSG:32637",
    )
    if destination.exists():
        destination.unlink()
    patches.to_file(destination, layer="patches", driver="GPKG")
    dissolved = patches.geometry.union_all()
    print(f"wrote {len(patches)} synthetic patches to {destination}")
    print(f"dissolved input area: {dissolved.area:.2f} square metres")
    print(f"convex hull area: {dissolved.convex_hull.area:.2f} square metres")


if __name__ == "__main__":
    main()
