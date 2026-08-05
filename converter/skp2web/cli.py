"""python -m skp2web <model.skp> -o <outdir>"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import sdk
from .assemblies import find_assemblies
from .emit import write
from .extract import extract
from .overlaps import find_overlaps
from .regions import CATEGORY_LABELS, build_regions


def convert(source: Path, out_dir: Path, include_hidden: bool = False, quiet: bool = False) -> dict:
    started = time.perf_counter()
    ex = extract(str(source), texture_dir=out_dir / "textures", include_hidden=include_hidden)
    regions = build_regions(ex)
    pairs, hidden = find_overlaps(ex, regions)
    for r in regions:
        r.hidden = min(hidden.get(r.id, 0.0), r.area)
    assemblies = find_assemblies(ex, regions)
    doc = write(ex, regions, out_dir, source, pairs, assemblies)
    doc["source"]["elapsedSeconds"] = round(time.perf_counter() - started, 2)
    if not quiet:
        _report(doc)
    return doc


def _report(doc: dict) -> None:
    stats = doc["stats"]
    print(f"  model      {doc['source']['modelName'] or '(unnamed)'}  (skp {doc['source']['skpVersion']})")
    print(f"  faces      {stats['faces']} -> {stats['regions']} regions")
    print(f"  triangles  {stats['triangles']}   vertices {stats['vertices']}")
    size = doc["bbox"]["size"]
    print(f"  extents    {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m")
    if stats["skippedHidden"]:
        print(f"  skipped    {stats['skippedHidden']} hidden entities")
    for a in doc["assemblies"]:
        print(f"  格柵       {a['name'][:34]}：{a['members']} 支合併為整片 "
              f"{a['widthM']:.2f} × {a['heightM']:.2f} m = {a['areaM2']:,.2f} m² "
              f"（逐面加總為 {a['rawAreaM2']:,.2f} m²）")
    ov = doc["overlaps"]
    if ov["pairCount"]:
        print(f"  overlaps   {ov['pairCount']} pairs, {ov['hiddenM2']:,.2f} m2 buried "
              f"({ov['hiddenM2'] / max(doc['totals']['areaM2'], 1e-9) * 100:.1f}% of all surface)")
    print("\n  material takeoff        全部面        扣除重疊")
    for row in doc["summary"]["byMaterial"]:
        print(f"    {row['areaM2']:>12,.2f} {row['exposedAreaM2']:>14,.2f} m2  "
              f"{row['regionCount']:>4} regions  {row['name']}")
    t = doc["totals"]
    print(f"    {t['areaM2']:>12,.2f} {t['exposedAreaM2']:>14,.2f} m2   合計")
    print("\n  by surface type")
    for row in doc["summary"]["byCategory"]:
        label = CATEGORY_LABELS.get(row["category"], row["category"])
        print(f"    {row['areaM2']:>12,.2f} m2  {row['regionCount']:>4} regions  {label}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="skp2web",
        description="Extract geometry, materials and dimensions from a SketchUp .skp file.",
    )
    ap.add_argument("source", type=Path, help="path to the .skp file")
    ap.add_argument("-o", "--out", type=Path, required=True, help="output directory")
    ap.add_argument(
        "--include-hidden",
        action="store_true",
        help="include entities on hidden tags (excluded by default so the takeoff "
             "matches what the model shows)",
    )
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    # A Windows console defaults to the regional code page - cp950 on a zh-TW
    # machine - which has no "m²", so the report below dies mid-print on the
    # very machines this tool is written for.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if not args.source.is_file():
        print(f"error: no such file: {args.source}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"reading {args.source.name}  [{sdk.DLL_PATH.parent.name}]")
    try:
        convert(args.source, args.out, args.include_hidden, args.quiet)
    except sdk.UnsupportedSkpVersion as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except sdk.SketchUpError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    if not args.quiet:
        print(f"\nwrote {args.out / 'model.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
