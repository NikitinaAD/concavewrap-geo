# concavewrap-geo

[![CI](https://github.com/NikitinaAD/concavewrap-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/NikitinaAD/concavewrap-geo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/concavewrap-geo.svg)](https://pypi.org/project/concavewrap-geo/)
[![Python](https://img.shields.io/pypi/pyversions/concavewrap-geo.svg)](https://pypi.org/project/concavewrap-geo/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Build auditable concave hulls that cover complete polygon areas.**

Many concave-hull implementations guarantee that the output contains the input
vertices. For areal data that is not enough: a hull edge can cut through a source
polygon. `concavewrap` repairs or rejects invalid input, constructs the hull, and
then enforces and verifies coverage of every source polygon.

![Polygon patches become a polygon-safe concave hull](https://raw.githubusercontent.com/NikitinaAD/concavewrap-geo/main/docs/demo.svg)

## Quick start

```bash
python -m pip install concavewrap-geo
concavewrap build areas.gpkg \
  --layer areas \
  --ratio 0.25 \
  --output hulls.gpkg \
  --diagnostics hulls.json
```

The output is a GeoPackage layer named `hulls`. The JSON report records input and
output areas, added fill area, the convex-hull area, coverage checks, repaired
features, and any convex fallback.

## Reproducible example

Create synthetic polygon patches arranged around a concavity, then build one hull:

```bash
python examples/make_example.py
concavewrap build examples/forest-patches.gpkg \
  --layer patches \
  --ratio 0.25 \
  --output examples/forest-hull.gpkg \
  --diagnostics examples/forest-hull.json
```

Expected audit values for the example are printed by the script and can be
recomputed from the resulting files. No external or real-world data is used.

## Ratio and policies

`--ratio` follows GEOS/Shapely semantics:

| value | behavior |
|---:|---|
| `0` | most concave result available from the input vertices |
| `0.25` | useful starting point for irregular polygon collections |
| `1` | convex hull |

The ratio is dimensionless. It is not an alpha radius or a distance threshold,
so values from alpha-shape tools cannot be copied directly.

| option | choices | meaning |
|---|---|---|
| `--scope` | `global`, `component` | bridge all polygons in a group, or keep disconnected dissolved components separate |
| `--group-by FIELD` | any scalar field | build an independent result for each attribute value |
| `--allow-holes` | flag | retain source holes and permit hull holes; without it all holes are filled |
| `--invalid` | `repair`, `error` | repair invalid polygonal geometry with GEOS or stop |
| `--fallback` | `convex`, `error` | use and report the convex hull if the concave operation fails, or stop |

## Guarantees

For every output record, `concavewrap` verifies that:

- the result is valid polygonal geometry;
- the result covers the complete input polygon area, not only its vertices;
- the result does not extend beyond the convex hull, within floating-point tolerance;
- the chosen hole, grouping, component, repair, and fallback policies are recorded;
- input ordering determines stable group and component ordering.

## Output fields

| field | meaning |
|---|---|
| `hull_id` | stable one-based output identifier |
| `group_value` | text representation of the grouping value, or null |
| `source_features` | number of input features contributing to the hull |
| `repaired_features` | number of invalid contributors repaired |
| `input_area` | dissolved source area in CRS square units |
| `hull_area` | output hull area |
| `fill_area` | area added around or between source polygons |
| `convex_area` | area of the corresponding convex hull |
| `hull_to_convex_ratio` | output area divided by convex-hull area |
| `fallback_used` | whether the convex fallback was used |
| `fallback_reason` | captured failure message, if any |
| `ratio`, `allow_holes`, `scope` | effective construction settings |
| `covers_input` | final invariant check |

## Python API

```python
import geopandas as gpd
from concavewrap import HullOptions, HullResult, build_hulls

areas = gpd.read_file("areas.gpkg", layer="areas")
result: HullResult = build_hulls(
    areas,
    HullOptions(ratio=0.25, scope="global", allow_holes=False),
)
result.hulls.to_file("hulls.gpkg", layer="hulls", driver="GPKG")
print(result.report())
```

The stable public interface is `build_hulls(...)`, `HullOptions`, `HullResult`,
and `HullDiagnostic`.

## Limits

- Input geometries must be Polygon or MultiPolygon.
- A projected CRS with horizontal units in metres is required so that area audit
  values are meaningful and comparable.
- `component` scope dissolves touching and overlapping polygons before identifying
  disconnected components.
- Concave hulls are not unique across algorithms. This package uses the GEOS
  algorithm exposed by Shapely and records its ratio explicitly.
- A hull is a generalization. Always inspect results for sparse samples, narrow
  necks, very large gaps, and geometries whose holes have semantic meaning.

Run `concavewrap --help` for all options. Exit code `0` means success and `2`
means invalid input or a processing failure.

## Development

```bash
python -m pip install -e ".[test]"
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Copyright 2026 Alena Nikitina. Licensed under the [Apache License 2.0](LICENSE).
