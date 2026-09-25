from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import box

from concavewrap.cli import main


def test_cli_writes_geopackage_and_diagnostics(tmp_path):
    source = tmp_path / "areas.gpkg"
    output = tmp_path / "hulls.gpkg"
    report = tmp_path / "report.json"
    gpd.GeoDataFrame(
        {"stand": ["A", "A"]},
        geometry=[box(0, 0, 2, 2), box(4, 0, 6, 2)],
        crs="EPSG:32637",
    ).to_file(source, layer="areas", driver="GPKG")

    code = main(
        [
            "build",
            str(source),
            "--layer",
            "areas",
            "--output",
            str(output),
            "--diagnostics",
            str(report),
            "--group-by",
            "stand",
        ]
    )

    assert code == 0
    assert len(gpd.read_file(output, layer="hulls")) == 1
    assert json.loads(report.read_text(encoding="utf-8"))["coverage_ok"] is True


def test_cli_rejects_non_geopackage_output(tmp_path, capsys):
    source = tmp_path / "areas.geojson"
    gpd.GeoDataFrame(geometry=[box(0, 0, 2, 2)], crs="EPSG:32637").to_file(source, driver="GeoJSON")

    code = main(["build", str(source), "--output", str(tmp_path / "hulls.geojson")])

    assert code == 2
    assert "output must use the .gpkg extension" in capsys.readouterr().err
