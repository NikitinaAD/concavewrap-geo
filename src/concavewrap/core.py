from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely import concave_hull, make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

Scope = Literal["global", "component"]
InvalidPolicy = Literal["repair", "error"]
FallbackPolicy = Literal["convex", "error"]


@dataclass(frozen=True)
class HullOptions:
    """Stable options for building polygon-safe concave hulls."""

    ratio: float = 0.3
    allow_holes: bool = False
    scope: Scope = "global"
    invalid: InvalidPolicy = "repair"
    fallback: FallbackPolicy = "convex"
    group_by: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.ratio <= 1.0:
            raise ValueError("ratio must be between 0 and 1")
        if self.scope not in {"global", "component"}:
            raise ValueError("scope must be 'global' or 'component'")
        if self.invalid not in {"repair", "error"}:
            raise ValueError("invalid must be 'repair' or 'error'")
        if self.fallback not in {"convex", "error"}:
            raise ValueError("fallback must be 'convex' or 'error'")


@dataclass(frozen=True)
class HullDiagnostic:
    hull_id: int
    group_value: str | None
    source_features: int
    repaired_features: int
    input_area: float
    hull_area: float
    fill_area: float
    convex_area: float
    hull_to_convex_ratio: float
    fallback_used: bool
    fallback_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HullResult:
    hulls: gpd.GeoDataFrame
    diagnostics: tuple[HullDiagnostic, ...]
    input_features: int
    repaired_features: int
    crs: str
    options: HullOptions

    def report(self) -> dict[str, object]:
        """Return a JSON-serializable diagnostics report."""

        return {
            "input_features": self.input_features,
            "repaired_features": self.repaired_features,
            "output_hulls": len(self.hulls),
            "crs": self.crs,
            "options": asdict(self.options),
            "coverage_ok": bool(self.hulls["covers_input"].all()),
            "total_input_area": float(self.hulls["input_area"].sum()),
            "total_hull_area": float(self.hulls["hull_area"].sum()),
            "total_convex_area": float(self.hulls["convex_area"].sum()),
            "hulls": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True)
class _Prepared:
    geometry: BaseGeometry
    repaired: bool
    group_value: object


def _projected_metric_crs(value: object) -> CRS:
    if value is None:
        raise ValueError("input layer must define a CRS")
    crs = CRS.from_user_input(value)
    if not crs.is_projected:
        raise ValueError("input CRS must be projected")
    axes = crs.axis_info[:2]
    if axes and any(abs((axis.unit_conversion_factor or 0.0) - 1.0) > 1e-9 for axis in axes):
        raise ValueError("projected CRS horizontal units must be metres")
    return crs


def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    parts: list[Polygon] = []
    for item in getattr(geometry, "geoms", ()):  # GeometryCollection after make_valid
        parts.extend(_polygon_parts(item))
    return parts


def _polygonal(geometry: BaseGeometry) -> BaseGeometry:
    parts = _polygon_parts(make_valid(geometry))
    if not parts:
        return Polygon()
    return unary_union(parts)


def _fill_holes(geometry: BaseGeometry) -> BaseGeometry:
    parts = _polygon_parts(geometry)
    return unary_union([Polygon(part.exterior) for part in parts]) if parts else Polygon()


def _holes(geometry: BaseGeometry) -> BaseGeometry:
    holes = [Polygon(ring) for part in _polygon_parts(geometry) for ring in part.interiors]
    return unary_union(holes) if holes else Polygon()


def _prepare(frame: gpd.GeoDataFrame, options: HullOptions) -> tuple[list[_Prepared], int]:
    if frame.empty:
        raise ValueError("input layer is empty")
    if options.group_by is not None and options.group_by not in frame.columns:
        raise ValueError(f"group-by column does not exist: {options.group_by}")

    prepared: list[_Prepared] = []
    repaired_count = 0
    for position, (_, row) in enumerate(frame.iterrows()):
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            raise ValueError(f"feature {position} has empty geometry")
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(
                f"feature {position} has {geometry.geom_type}; "
                "only Polygon/MultiPolygon are supported"
            )

        repaired = not geometry.is_valid
        if repaired and options.invalid == "error":
            raise ValueError(f"feature {position} has invalid geometry")
        normalized = _polygonal(geometry if not repaired else make_valid(geometry))
        if normalized.is_empty:
            raise ValueError(f"feature {position} has no polygonal area after validation")
        if repaired:
            repaired_count += 1
        group_value = row[options.group_by] if options.group_by is not None else None
        prepared.append(_Prepared(normalized, repaired, group_value))
    return prepared, repaired_count


def _group_token(value: object) -> tuple[str, object]:
    try:
        if bool(pd.isna(value)):
            return ("null", "")
    except (TypeError, ValueError):
        pass
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError("group-by values must be scalar and hashable") from exc
    return (type(value).__name__, value)


def _group_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _units_for_group(items: list[_Prepared], scope: Scope) -> list[BaseGeometry]:
    dissolved = _polygonal(unary_union([item.geometry for item in items]))
    if dissolved.is_empty:
        raise ValueError("a group has no polygonal area")
    if scope == "global":
        return [dissolved]
    return sorted(
        _polygon_parts(dissolved),
        key=lambda part: (part.bounds[0], part.bounds[1], part.bounds[2], part.bounds[3]),
    )


def _safe_hull(source: BaseGeometry, options: HullOptions) -> tuple[BaseGeometry, bool, str | None]:
    convex = source.convex_hull
    fallback_used = False
    fallback_reason: str | None = None
    try:
        raw = concave_hull(source, ratio=options.ratio, allow_holes=options.allow_holes)
        candidate = _polygonal(raw)
        if candidate.is_empty:
            raise ValueError("concave hull returned no polygonal area")

        # GEOS concave hull covers input vertices, not necessarily every point of an
        # areal feature. Union with the source establishes the package's area-coverage
        # guarantee while keeping the result inside the convex hull.
        candidate = _polygonal(candidate.union(source))
        if options.allow_holes:
            candidate = _polygonal(candidate.difference(_holes(source)))
        else:
            candidate = _polygonal(_fill_holes(candidate))
        outside_area = candidate.difference(convex).area
        tolerance = max(1e-9, convex.area * 1e-12)
        if outside_area > tolerance:
            raise ValueError("concave hull extends outside the convex hull")
        if not candidate.covers(source):
            raise ValueError("concave hull does not cover the complete input area")
    except Exception as exc:
        if options.fallback == "error":
            raise ValueError(f"concave hull failed: {exc}") from exc
        candidate = convex
        fallback_used = True
        fallback_reason = str(exc)

    candidate = _polygonal(make_valid(candidate))
    if candidate.is_empty or not candidate.covers(source):
        raise ValueError("failed to construct a valid hull covering the input")
    return candidate, fallback_used, fallback_reason


def build_hulls(frame: gpd.GeoDataFrame, options: HullOptions | None = None) -> HullResult:
    """Build audited concave hulls that cover complete polygon input areas.

    ``ratio=0`` requests the most concave GEOS result and ``ratio=1`` is the
    convex hull. ``scope='global'`` builds one hull per group; ``component``
    builds one hull for each disconnected component after dissolving overlaps.
    """

    options = options or HullOptions()
    crs = _projected_metric_crs(frame.crs)
    prepared, repaired_count = _prepare(frame, options)

    groups: dict[tuple[str, object], list[_Prepared]] = {}
    values: dict[tuple[str, object], object] = {}
    for item in prepared:
        token = _group_token(item.group_value) if options.group_by is not None else ("all", "")
        groups.setdefault(token, []).append(item)
        values.setdefault(token, item.group_value)

    rows: list[dict[str, object]] = []
    diagnostics: list[HullDiagnostic] = []
    hull_id = 1
    for token, items in groups.items():
        group_value = values[token] if options.group_by is not None else None
        for source in _units_for_group(items, options.scope):
            contributors = [item for item in items if item.geometry.intersects(source)]
            hull, fallback_used, fallback_reason = _safe_hull(source, options)
            convex_area = float(source.convex_hull.area)
            input_area = float(source.area)
            hull_area = float(hull.area)
            diagnostic = HullDiagnostic(
                hull_id=hull_id,
                group_value=_group_text(group_value),
                source_features=len(contributors),
                repaired_features=sum(item.repaired for item in contributors),
                input_area=input_area,
                hull_area=hull_area,
                fill_area=hull_area - input_area,
                convex_area=convex_area,
                hull_to_convex_ratio=(hull_area / convex_area if convex_area else 1.0),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )
            diagnostics.append(diagnostic)
            rows.append(
                {
                    **diagnostic.to_dict(),
                    "ratio": options.ratio,
                    "allow_holes": options.allow_holes,
                    "scope": options.scope,
                    "covers_input": bool(hull.covers(source)),
                    "geometry": hull,
                }
            )
            hull_id += 1

    hulls = gpd.GeoDataFrame(rows, geometry="geometry", crs=frame.crs)
    return HullResult(
        hulls=hulls,
        diagnostics=tuple(diagnostics),
        input_features=len(frame),
        repaired_features=repaired_count,
        crs=crs.to_string(),
        options=options,
    )
