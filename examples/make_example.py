from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

ROOT = Path(__file__).parent
OUTPUT = ROOT / "generated"


def _write(name: str, geometries, **columns) -> None:
    destination = OUTPUT / f"{name}.gpkg"
    frame = gpd.GeoDataFrame(columns, geometry=geometries, crs="EPSG:32637")
    if destination.exists():
        destination.unlink()
    frame.to_file(destination, layer="areas", driver="GPKG", index=False)
    print(f"{name:12} features={len(frame)} dissolved_area={frame.geometry.union_all().area:.2f}")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    _write(
        "forest-patches",
        [
            box(0, 0, 3, 8),
            box(3, 6, 10, 8),
            box(8, 3, 10, 6),
            box(3, 0, 6, 2),
        ],
        patch_id=["west", "north", "east", "south-west"],
        stand=["demo"] * 4,
    )
    _write(
        "large-gap",
        [box(0, 0, 4, 4), box(12, 0, 16, 4)],
        patch_id=["west", "east"],
    )
    _write(
        "narrow-neck",
        [box(0, 0, 4, 4), box(4, 1.8, 10, 2.2), box(10, 0, 14, 4)],
        patch_id=["west", "neck", "east"],
    )
    _write(
        "ring-with-hole",
        [
            box(0, 0, 8, 1),
            box(0, 7, 8, 8),
            box(0, 1, 1, 7),
            box(7, 1, 8, 7),
        ],
        patch_id=["south", "north", "west", "east"],
    )
    print(f"Wrote synthetic polygon examples to {OUTPUT}")


if __name__ == "__main__":
    main()
