from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box

from concavewrap import HullOptions, build_hulls

CRS = "EPSG:32637"


def frame(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=geometries, crs=CRS)


def c_shape():
    return [
        box(0, 0, 4, 1),
        box(0, 3, 4, 4),
        box(0, 1, 1, 3),
    ]


def test_global_hull_covers_complete_polygon_areas():
    source = frame(c_shape())
    result = build_hulls(source, HullOptions(ratio=0.0))
    dissolved = source.geometry.union_all()
    hull = result.hulls.geometry.iloc[0]

    assert hull.covers(dissolved)
    assert hull.area >= dissolved.area
    assert hull.area <= dissolved.convex_hull.area
    assert result.report()["coverage_ok"] is True
    assert result.hulls.iloc[0]["source_features"] == 3


def test_ratio_one_is_convex_hull():
    source = frame(c_shape())
    result = build_hulls(source, HullOptions(ratio=1.0))
    assert result.hulls.geometry.iloc[0].equals(source.geometry.union_all().convex_hull)


def test_component_scope_keeps_disconnected_areas_separate():
    source = frame([box(0, 0, 2, 2), box(10, 0, 12, 2)])
    global_result = build_hulls(source)
    component_result = build_hulls(source, HullOptions(scope="component"))

    assert len(global_result.hulls) == 1
    assert len(component_result.hulls) == 2
    assert component_result.hulls.geometry.iloc[0].covers(source.geometry.iloc[0])
    assert component_result.hulls.geometry.iloc[1].covers(source.geometry.iloc[1])


def test_group_by_builds_one_hull_per_group_and_preserves_order():
    source = frame(
        [box(0, 0, 1, 1), box(2, 0, 3, 1), box(20, 0, 21, 1)],
        stand=["A", "A", "B"],
    )
    result = build_hulls(source, HullOptions(group_by="stand"))

    assert list(result.hulls["group_value"]) == ["A", "B"]
    assert list(result.hulls["source_features"]) == [2, 1]


def test_hole_policy_is_explicit():
    ring = frame(
        [
            box(0, 0, 4, 1),
            box(0, 3, 4, 4),
            box(0, 1, 1, 3),
            box(3, 1, 4, 3),
        ]
    )
    with_holes = build_hulls(ring, HullOptions(ratio=0.0, allow_holes=True))
    filled = build_hulls(ring, HullOptions(ratio=0.0, allow_holes=False))

    assert len(with_holes.hulls.geometry.iloc[0].interiors) == 1
    assert len(filled.hulls.geometry.iloc[0].interiors) == 0
    assert filled.hulls.geometry.iloc[0].area > with_holes.hulls.geometry.iloc[0].area


def test_invalid_polygon_can_be_repaired_or_rejected():
    bow_tie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    source = frame([bow_tie])

    repaired = build_hulls(source, HullOptions(invalid="repair"))
    assert repaired.repaired_features == 1
    assert repaired.hulls.geometry.iloc[0].is_valid
    with pytest.raises(ValueError, match="invalid geometry"):
        build_hulls(source, HullOptions(invalid="error"))


def test_multipolygon_input_is_supported():
    geometry = MultiPolygon([box(0, 0, 1, 1), box(3, 0, 4, 1)])
    result = build_hulls(frame([geometry]))
    assert result.hulls.geometry.iloc[0].covers(geometry)


def test_convex_fallback_is_reported(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic GEOS failure")

    monkeypatch.setattr("concavewrap.core.concave_hull", fail)
    source = frame(c_shape())
    result = build_hulls(source, HullOptions(fallback="convex"))

    row = result.hulls.iloc[0]
    assert row["fallback_used"]
    assert "synthetic GEOS failure" in row["fallback_reason"]
    assert row.geometry.equals(source.geometry.union_all().convex_hull)


def test_error_fallback_propagates_failure(monkeypatch):
    monkeypatch.setattr(
        "concavewrap.core.concave_hull",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failure")),
    )
    with pytest.raises(ValueError, match="concave hull failed"):
        build_hulls(frame(c_shape()), HullOptions(fallback="error"))


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_ratio_bounds(ratio):
    with pytest.raises(ValueError, match="between 0 and 1"):
        HullOptions(ratio=ratio)


def test_rejects_geographic_crs_and_non_polygon_input():
    geographic = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    with pytest.raises(ValueError, match="projected"):
        build_hulls(geographic)

    points = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=CRS)
    with pytest.raises(ValueError, match="Polygon/MultiPolygon"):
        build_hulls(points)


def test_rejects_non_metric_projected_crs_and_missing_group_column():
    feet = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:2263")
    with pytest.raises(ValueError, match="metres"):
        build_hulls(feet)

    with pytest.raises(ValueError, match="group-by column"):
        build_hulls(frame([box(0, 0, 1, 1)]), HullOptions(group_by="missing"))
