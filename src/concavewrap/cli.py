from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd

from . import __version__
from .core import HullOptions, build_hulls


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="concavewrap",
        description="Build auditable concave hulls that cover complete polygon areas.",
    )
    parser.add_argument("--version", action="version", version=f"concavewrap {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build hulls from a polygon layer")
    build.add_argument("input", type=Path)
    build.add_argument("--layer", help="input layer name for multi-layer datasets")
    build.add_argument("--output", type=Path, required=True, help="output GeoPackage")
    build.add_argument("--output-layer", default="hulls")
    build.add_argument("--diagnostics", type=Path, help="diagnostics JSON path")
    build.add_argument("--ratio", type=float, default=0.3)
    build.add_argument("--scope", choices=("global", "component"), default="global")
    build.add_argument("--group-by")
    build.add_argument("--allow-holes", action="store_true")
    build.add_argument("--invalid", choices=("repair", "error"), default="repair")
    build.add_argument("--fallback", choices=("convex", "error"), default="convex")
    return parser


def _run_build(args: argparse.Namespace) -> int:
    if args.output.suffix.lower() != ".gpkg":
        raise ValueError("output must use the .gpkg extension")
    if args.output.resolve() == args.input.resolve():
        raise ValueError("output must differ from input")
    read_options = {"layer": args.layer} if args.layer else {}
    frame = gpd.read_file(args.input, **read_options)
    options = HullOptions(
        ratio=args.ratio,
        allow_holes=args.allow_holes,
        scope=args.scope,
        invalid=args.invalid,
        fallback=args.fallback,
        group_by=args.group_by,
    )
    result = build_hulls(frame, options)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    result.hulls.to_file(args.output, layer=args.output_layer, driver="GPKG")

    diagnostics = args.diagnostics or args.output.with_suffix(".diagnostics.json")
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.write_text(json.dumps(result.report(), indent=2), encoding="utf-8")
    print(f"wrote {len(result.hulls)} hull(s) to {args.output} and diagnostics to {diagnostics}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return _run_build(args)
    except Exception as exc:
        print(f"concavewrap: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
