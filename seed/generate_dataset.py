#!/usr/bin/env python3
"""
Generates a synthetic EcoTaxa import bundle: a handful of "samples" (stations),
each with its own TSV + JPEG images, zipped into the layout EcoTaxa expects
(one zip containing several sample directories, not zipped as a single root).

Everything is deterministic (fixed random seed) so re-running produces the
same dataset, which is what you want after a `docker compose down -v` rebuild.

Categories are real taxonomy names/ids pulled from EcoTaxoServer (see
../seed/import_dataset.py, which calls /taxa/pull_from_central before
importing) -- using object_annotation_category_id directly bypasses the
TSV's name-matching step entirely, so imports never stall waiting on
unresolved taxa.

Image "morphometrics" (area, major/minor axis, elongation...) are computed
from the actual generated shape geometry, so they carry real per-category
signal -- useful if you want to sanity check a toy classifier against them.
"""
import csv
import io
import json
import math
import os
import random
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
BUILD_DIR = HERE / "build"
OUT_ZIP = HERE.parent / "file_srv" / "seed_dataset.zip"

SEED = int(os.environ.get("SEED_RANDOM_SEED", "42"))
TOTAL_OBJECTS = int(os.environ.get("SEED_OBJECT_COUNT", "600"))
VALIDATED_FRACTION = float(os.environ.get("SEED_VALIDATED_FRACTION", "0.7"))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "administrator@mail.test")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "EcoTaxa Admin")

# name, taxonomy id (from EcoTaxoServer, verified to exist after a pull_from_central),
# hue (0-360), base aspect ratio (major/minor), base size in px (diameter-ish)
CATEGORIES = [
    ("Copepoda", 25828, 40, 2.6, 70),
    ("Calanoida", 45074, 45, 2.8, 65),
    ("Cyclopoida", 45072, 50, 2.3, 55),
    ("Oncaeidae", 78418, 55, 2.0, 40),
    ("Harpacticoida", 45071, 35, 3.0, 50),
    ("Chaetognatha", 11514, 200, 6.0, 110),
    ("Appendicularia", 85123, 190, 1.6, 60),
    ("Ostracoda", 30815, 30, 1.3, 45),
    ("Euphausiacea", 45041, 25, 4.5, 100),
    ("Amphipoda", 45054, 20, 3.2, 80),
    ("Decapoda", 45043, 15, 2.5, 95),
    ("Cladocera", 45036, 60, 1.4, 50),
    ("Foraminifera", 11758, 300, 1.1, 35),
    ("Radiolaria", 94043, 280, 1.2, 45),
    ("Ciliophora", 2250, 320, 1.5, 30),
    ("Annelida", 11518, 10, 5.5, 90),
    ("Gastropoda", 12905, 260, 1.3, 55),
    ("Hydrozoa", 12865, 220, 1.8, 75),
    ("Siphonophorae", 25990, 230, 3.5, 120),
    ("Doliolida", 25944, 180, 1.2, 85),
    ("Salpida", 25942, 170, 1.4, 100),
    ("Polychaeta", 12838, 5, 4.8, 90),
    ("Thecosomata", 91704, 240, 1.3, 60),
    ("Bryozoa", 11515, 100, 1.6, 50),
    ("Echinodermata", 11509, 340, 1.1, 65),
    ("Mollusca", 11498, 250, 1.4, 70),
]

SAMPLES = [
    {
        "sample_id": "seed_station_a",
        "lat": 43.685,
        "lon": 7.315,
        "date": "20260601",
        "ship": "seed_vessel",
        "gear": "net",
    },
    {
        "sample_id": "seed_station_b",
        "lat": -12.02,
        "lon": 55.44,
        "date": "20260615",
        "ship": "seed_vessel",
        "gear": "net",
    },
    {
        "sample_id": "seed_station_c",
        "lat": 36.7,
        "lon": -122.1,
        "date": "20260703",
        "ship": "seed_vessel_2",
        "gear": "bongo",
    },
]

# Known-good column layout + boilerplate values, taken from ecotaxa_back's own
# import test fixtures (QA/py/data/import_test), so process_*/acq_* metadata
# columns are values EcoTaxa is already known to accept.
TEMPLATE_HEADER = [
    "object_id",
    "object_lat",
    "object_lon",
    "object_date",
    "object_time",
    "object_depth_min",
    "object_depth_max",
    "object_annotation_status",
    "object_annotation_person_name",
    "object_annotation_person_email",
    "object_annotation_date",
    "object_annotation_time",
    "object_annotation_category_id",
    "img_file_name",
    "img_rank",
    "object_width",
    "object_height",
    "object_area",
    "object_mean",
    "object_major",
    "object_minor",
    "object_feret",
    "object_esd",
    "object_elongation",
    "sample_id",
    "sample_project",
    "sample_ship",
    "sample_samplinggear",
    "process_id",
    "process_software",
    "acq_id",
    "acq_instrument",
]
TEMPLATE_TYPES = {
    "object_id": "t",
    "object_lat": "f",
    "object_lon": "f",
    "object_date": "t",
    "object_time": "t",
    "object_depth_min": "f",
    "object_depth_max": "f",
    "object_annotation_status": "t",
    "object_annotation_person_name": "t",
    "object_annotation_person_email": "t",
    "object_annotation_date": "t",
    "object_annotation_time": "t",
    "object_annotation_category_id": "t",
    "img_file_name": "t",
    "img_rank": "t",
    "object_width": "f",
    "object_height": "f",
    "object_area": "f",
    "object_mean": "f",
    "object_major": "f",
    "object_minor": "f",
    "object_feret": "f",
    "object_esd": "f",
    "object_elongation": "f",
    "sample_id": "t",
    "sample_project": "t",
    "sample_ship": "t",
    "sample_samplinggear": "t",
    "process_id": "t",
    "process_software": "t",
    "acq_id": "t",
    "acq_instrument": "t",
}


def zipf_weights(n, s=0.9):
    raw = [1.0 / ((i + 1) ** s) for i in range(n)]
    total = sum(raw)
    return [r / total for r in raw]


def make_image(rng: random.Random, hue, aspect, size, jpg_path: Path):
    """Draw a blob loosely shaped/colored like the category, on a noisy grey
    background (mimics a plankton-imaging-system frame), and return the
    morphometrics computed from the actual drawn ellipse."""
    canvas = size + rng.randint(20, 40)
    img = Image.new("L", (canvas, canvas), color=235)
    # background noise
    noise = Image.effect_noise((canvas, canvas), 12).convert("L")
    img = Image.blend(img, noise, 0.08)
    draw = ImageDraw.Draw(img)

    minor = size / math.sqrt(aspect * rng.uniform(0.85, 1.15))
    major = minor * aspect * rng.uniform(0.85, 1.15)
    cx, cy = canvas / 2, canvas / 2
    angle = rng.uniform(0, 180)

    ellipse_img = Image.new("L", (canvas, canvas), 255)
    edraw = ImageDraw.Draw(ellipse_img)
    grey = rng.randint(30, 90)
    bbox = (cx - major / 2, cy - minor / 2, cx + major / 2, cy + minor / 2)
    edraw.ellipse(bbox, fill=grey)
    ellipse_img = ellipse_img.rotate(angle, center=(cx, cy), fillcolor=255)
    img = Image.composite(ellipse_img, img, ellipse_img.point(lambda p: 255 if p < 250 else 0))
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(jpg_path, "JPEG", quality=88)

    area = math.pi * (major / 2) * (minor / 2)
    esd = math.sqrt(4 * area / math.pi)
    feret = major
    return {
        "width": canvas,
        "height": canvas,
        "area": round(area, 1),
        "mean": grey,
        "major": round(major, 2),
        "minor": round(minor, 2),
        "feret": round(feret, 2),
        "esd": round(esd, 2),
        "elongation": round(major / minor, 3),
    }


def build():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    rng = random.Random(SEED)
    weights = zipf_weights(len(CATEGORIES))

    counts_per_sample = TOTAL_OBJECTS // len(SAMPLES)
    summary = {"total": 0, "by_category": {}, "by_status": {"validated": 0, "predicted": 0}}

    for sample in SAMPLES:
        sample_dir = BUILD_DIR / sample["sample_id"]
        img_dir = sample_dir
        rows = []
        for n in range(1, counts_per_sample + 1):
            cat_name, cat_id, hue, aspect, size = rng.choices(CATEGORIES, weights=weights, k=1)[0]
            object_id = f"{sample['sample_id']}_{n:04d}"
            img_name = f"{object_id}.jpg"
            morpho = make_image(rng, hue, aspect, size, img_dir / img_name)

            is_validated = rng.random() < VALIDATED_FRACTION
            status = "validated" if is_validated else "predicted"
            summary["by_status"][status] += 1
            summary["by_category"].setdefault(cat_name, 0)
            summary["by_category"][cat_name] += 1
            summary["total"] += 1

            lat = sample["lat"] + rng.uniform(-0.05, 0.05)
            lon = sample["lon"] + rng.uniform(-0.05, 0.05)
            hh = rng.randint(0, 23)
            mm = rng.randint(0, 59)
            depth_min = round(rng.uniform(0, 400), 1)
            depth_max = depth_min + round(rng.uniform(5, 200), 1)

            row = {
                "object_id": object_id,
                "object_lat": f"{lat:.6f}",
                "object_lon": f"{lon:.6f}",
                "object_date": sample["date"],
                "object_time": f"{hh:02d}{mm:02d}00",
                "object_depth_min": depth_min,
                "object_depth_max": depth_max,
                "object_annotation_status": status,
                "object_annotation_person_name": ADMIN_NAME if is_validated else "",
                "object_annotation_person_email": ADMIN_EMAIL if is_validated else "",
                "object_annotation_date": sample["date"] if is_validated else "",
                "object_annotation_time": f"{hh:02d}{mm:02d}00" if is_validated else "",
                "object_annotation_category_id": cat_id,
                "img_file_name": img_name,
                "img_rank": "0",
                "object_width": morpho["width"],
                "object_height": morpho["height"],
                "object_area": morpho["area"],
                "object_mean": morpho["mean"],
                "object_major": morpho["major"],
                "object_minor": morpho["minor"],
                "object_feret": morpho["feret"],
                "object_esd": morpho["esd"],
                "object_elongation": morpho["elongation"],
                "sample_id": sample["sample_id"],
                "sample_project": "ecotaxa-test seed data",
                "sample_ship": sample["ship"],
                "sample_samplinggear": sample["gear"],
                "process_id": f"seed_process_{sample['sample_id']}",
                "process_software": "seed/generate_dataset.py",
                "acq_id": f"seed_acq_{sample['sample_id']}",
                "acq_instrument": "synthetic",
            }
            rows.append(row)

        tsv_path = sample_dir / f"ecotaxa_{sample['sample_id']}.tsv"
        with tsv_path.open("w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(TEMPLATE_HEADER)
            w.writerow([f"[{TEMPLATE_TYPES[c]}]" for c in TEMPLATE_HEADER])
            for row in rows:
                w.writerow([row[c] for c in TEMPLATE_HEADER])

    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for sample in SAMPLES:
            sample_dir = BUILD_DIR / sample["sample_id"]
            for path in sample_dir.rglob("*"):
                zf.write(path, arcname=str(path.relative_to(BUILD_DIR)))

    summary_path = HERE / "build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Built {summary['total']} objects across {len(SAMPLES)} samples -> {OUT_ZIP}")
    print(f"Status split: {summary['by_status']}")
    return summary


if __name__ == "__main__":
    build()
