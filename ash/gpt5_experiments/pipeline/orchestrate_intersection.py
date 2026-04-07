"""
Orchestrator: intersection PMIDs → text download → anchor extraction → grounded JSONs.

Usage:
    uv run --active python orchestrate_intersection.py           # default: 1000 PMIDs
    uv run --active python orchestrate_intersection.py --limit 500

Two-stage checkpointing:
  - Text download: skipped if <pmid>.txt already exists in txt_archive
  - Extraction:    skipped if <pmid>.json already exists in output_dir

Re-running safely resumes from wherever it left off.

Output: ash/gpt5_experiments/dataset_intersection/raw_anchor/
"""

import csv
import gzip
import logging
import os
import pickle
import shutil
import subprocess
import sys
import tarfile
import argparse
from pathlib import Path

import pystow
import requests
from openai import OpenAI

from extractor_anchor import process_pmid

output_dir  = pystow.module("indra", "cogex", "clinical_trial_results", "raw").base
txt_archive = pystow.module("trialsynth", "content", "txt").base
pdf_archive = pystow.module("trialsynth", "content", "pdfs").base
temp_work   = pystow.module("trialsynth", "content", "temp").base

logger = logging.getLogger(__name__)

from indra.literature.pubmed_client import get_pmid_to_package_url_mapping, get_abstract


def get_intersection_pmids(limit: int = None) -> list[str]:
    """Return intersection PMIDs (registry RESULT links ∩ PubMed scan), up to `limit`."""
    pkl_path = pystow.module("trialsynth", "clinicaltrials").base / "clinicaltrials.pkl.gz"
    csv_path = pystow.module("trialsynth", "link_discovery").base / "pubmed_nct_links.csv"

    logger.info("Loading registry result links...")
    registry_result_links = set()
    with gzip.open(pkl_path, "rb") as f:
        trials = pickle.load(f)
    for trial in trials:
        if trial.references:
            for ref in trial.references:
                pmid = ref[0] if isinstance(ref, (tuple, list)) else ref
                ref_type = str(ref[1]).upper() if isinstance(ref, (tuple, list)) and len(ref) > 1 else ""
                if pmid and "RESULT" in ref_type:
                    registry_result_links.add(pmid)

    logger.info("Loading PubMed scan links...")
    pubmed_pmids = set()
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) >= 2:
                pubmed_pmids.add(row[0])

    intersection = sorted(registry_result_links & pubmed_pmids)
    logger.info(f"Intersection size: {len(intersection)}.")
    if limit:
        intersection = intersection[:limit]
        logger.info(f"Capped to {len(intersection)} PMIDs.")
    return intersection


def download_file(url: str, dest: Path) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception:
        return False


def download_texts(pmids: list[str]):
    logger.info(f"Downloading text for {len(pmids)} PMIDs...")
    mappings = get_pmid_to_package_url_mapping()
    extractor_util = Path(__file__).parent / "extract.py"

    for i, pmid in enumerate(pmids):
        if (txt_archive / f"{pmid}.txt").exists():
            logger.info(f"[{i+1}/{len(pmids)}] {pmid} already cached.")
            continue

        for item in temp_work.glob("*"):
            if item.is_file():
                os.remove(item)
            elif item.is_dir():
                shutil.rmtree(item)

        try:
            localized = False
            source = ""
            package_url = mappings.get(pmid)

            if package_url:
                pkg_path = temp_work / f"temp_{pmid}.tar.gz"
                if download_file(package_url, pkg_path):
                    extract_path = temp_work / f"extract_{pmid}"
                    try:
                        with tarfile.open(pkg_path, "r:gz") as tar:
                            tar.extractall(path=extract_path)
                        pdfs = list(extract_path.rglob("*.pdf"))
                        if pdfs:
                            shutil.move(str(pdfs[0]), str(temp_work / f"{pmid}.pdf"))
                            localized = True
                            source = "PMC"
                    except Exception:
                        pass

            if not localized:
                abstract = get_abstract(pmid, prepend_title=True)
                if abstract:
                    with open(txt_archive / f"{pmid}.txt", "w", encoding="utf-8") as f:
                        f.write(abstract)
                    localized = True
                    source = "ABS"

            if localized:
                if source == "PMC":
                    subprocess.run(
                        [sys.executable, str(extractor_util)],
                        cwd=str(temp_work),
                        capture_output=True,
                    )
                    for txt_file in temp_work.glob("*.txt"):
                        shutil.move(str(txt_file), str(txt_archive / txt_file.name))
                    for pdf_file in temp_work.glob("*.pdf"):
                        shutil.move(str(pdf_file), str(pdf_archive / pdf_file.name))
                logger.info(f"[{i+1}/{len(pmids)}] {pmid} ({source}) - OK")
            else:
                logger.warning(f"[{i+1}/{len(pmids)}] {pmid} - NO CONTENT")

        except Exception as e:
            logger.error(f"[{i+1}/{len(pmids)}] {pmid} - FAILED: {e}")


def run_extraction(pmids: list[str]):
    logger.info(f"Running anchor extraction on {len(pmids)} PMIDs...")
    client = OpenAI()
    stats = []

    for pmid in pmids:
        row = process_pmid(pmid, client, txt_archive, output_dir)
        stats.append(row)
        if row["status"] == "ok":
            logger.info(f"  {pmid} extracted ({row['output_tokens']} output tokens)")
        elif row["status"] == "skipped":
            logger.info(f"  {pmid} skipped (already exists)")
        else:
            logger.warning(f"  {pmid} -> {row['status']}")

    completed = [r for r in stats if r["status"] == "ok"]
    skipped   = sum(1 for r in stats if r["status"] == "skipped")
    missing   = sum(1 for r in stats if r["status"] == "missing_text")
    errors    = sum(1 for r in stats if r["status"] not in ("ok", "skipped", "missing_text"))

    logger.info(f"Extraction complete: {len(completed)} new, {skipped} skipped, {missing} missing text, {errors} errors")
    if completed:
        total_out = sum(r["output_tokens"] for r in completed)
        logger.info(f"Avg output tokens/paper: {total_out // len(completed)}")

    csv_path = pystow.module("indra", "cogex", "clinical_trial_results").base / "extraction_stats.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pmid", "status", "input_tokens", "output_tokens"])
        writer.writeheader()
        writer.writerows(stats)
    logger.info(f"Stats saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000, help="Max PMIDs to process (default: 1000)")
    args = parser.parse_args()

    pmids_path = pystow.module("indra", "cogex", "clinical_trial_results").base / "intersection_pmids.txt"

    if pmids_path.exists():
        with open(pmids_path, "r") as f:
            saved = [line.strip() for line in f if line.strip()]
    else:
        saved = []

    if len(saved) >= args.limit:
        pmids = saved[:args.limit]
        logger.info(f"Loaded {len(pmids)} PMIDs from {pmids_path}")
    else:
        pmids = get_intersection_pmids(limit=args.limit)
        with open(pmids_path, "w") as f:
            for pmid in pmids:
                f.write(pmid + "\n")
        logger.info(f"Saved {len(pmids)} PMIDs to {pmids_path}")

    for d in [output_dir, txt_archive, pdf_archive, temp_work]:
        d.mkdir(parents=True, exist_ok=True)

    download_texts(pmids)
    run_extraction(pmids)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
