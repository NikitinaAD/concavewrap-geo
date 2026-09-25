"""Generate and process all documented concavewrap scenarios."""

from __future__ import annotations

import json

import geopandas as gpd
from make_example import OUTPUT
from make_example import main as make_example

from concavewrap import HullOptions, build_hulls


def _run(name: str, source: str, options: HullOptions):
    frame = gpd.read_file(OUTPUT / f"{source}.gpkg", layer="areas")
    result = build_hulls(frame, options)
    destination = OUTPUT / f"{name}.gpkg"
    if destination.exists():
        destination.unlink()
    result.hulls.to_file(destination, layer="hulls", driver="GPKG", index=False)
    report = result.report()
    (OUTPUT / f"{name}.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{name:18} hulls={report['output_hulls']} "
        f"coverage={report['coverage_ok']} area={report['total_hull_area']:.2f}"
    )
    return result


def _hole_count(result) -> int:
    return sum(
        len(part.interiors)
        for geometry in result.hulls.geometry
        for part in (geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry])
    )


def main() -> None:
    make_example()
    standard = _run("forest-hull", "forest-patches", HullOptions(ratio=0.25))
    gap_global = _run("gap-global", "large-gap", HullOptions(ratio=0.25, scope="global"))
    gap_components = _run(
        "gap-components",
        "large-gap",
        HullOptions(ratio=0.25, scope="component"),
    )
    narrow = _run("narrow-neck-hull", "narrow-neck", HullOptions(ratio=0.15))
    ring_keep = _run(
        "ring-keep-hole",
        "ring-with-hole",
        HullOptions(ratio=0.0, allow_holes=True),
    )
    ring_fill = _run(
        "ring-fill-hole",
        "ring-with-hole",
        HullOptions(ratio=0.0, allow_holes=False),
    )

    if not all(result.report()["coverage_ok"] for result in (standard, narrow)):
        raise AssertionError("every standard hull must cover its complete source area")
    if len(gap_global.hulls) != 1 or len(gap_components.hulls) != 2:
        raise AssertionError("global/component gap behavior changed")
    if _hole_count(ring_keep) != 1 or _hole_count(ring_fill) != 0:
        raise AssertionError("explicit hole policy changed")

    summary = {
        "forest_hull": standard.report(),
        "gap_global": gap_global.report(),
        "gap_components": gap_components.report(),
        "narrow_neck": narrow.report(),
        "ring_keep_hole": ring_keep.report(),
        "ring_fill_hole": ring_fill.report(),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
