"""
Orchestrator: intersection PMIDs -> text download -> anchor extraction -> grounded JSONs.

Usage:
    python orchestrate.py           # default: 1000 PMIDs
    python orchestrate.py --limit 500

Two-stage checkpointing:
  - Text download: skipped if <pmid>.txt already exists in txt_archive
  - Extraction:    skipped if <pmid>.json already exists in output_dir

Re-running safely resumes from wherever it left off.
"""

import csv
import gzip
import logging
import os
import pickle
import shutil
import tarfile
import argparse
from collections import Counter
from pathlib import Path

import tqdm
import pystow
import requests
from openai import OpenAI
from pypdf import PdfReader
from indra.literature.pubmed_client import get_pmid_to_package_url_mapping, get_abstract

from trialsynth.base.extract.extract import process_pmid

output_dir  = pystow.module("indra", "cogex", "clinical_trial_results", "raw")
txt_archive = pystow.module("trialsynth", "content", "txt")
pdf_archive = pystow.module("trialsynth", "content", "pdfs")
temp_work   = pystow.module("trialsynth", "content", "temp")
trial_pkl_path = pystow.join("trialsynth", "clinicaltrials", name="clinicaltrials.pkl.gz")
pubmed_nct_links_path = pystow.join("trialsynth", "clinicaltrials", name="pubmed_nct_links.csv")

logger = logging.getLogger('trialsynth.base.extract.orchestrate')


def get_intersection_pmids(limit: int = None) -> list[str]:
    """Return intersection PMIDs (registry RESULT links intersect PubMed scan), up to `limit`."""

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

    for pmid in tqdm.tqdm(pmids):
        if txt_archive.join(name=f"{pmid}.txt").exists():
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
                pkg_path = temp_work.join(name=f"temp_{pmid}.tar.gz")
                if download_file(package_url, pkg_path):
                    extract_path = temp_work.join(f"extract_{pmid}")
                    try:
                        with tarfile.open(pkg_path, "r:gz") as tar:
                            tar.extractall(path=extract_path)
                        pdfs = list(extract_path.rglob("*.pdf"))
                        if pdfs:
                            shutil.move(str(pdfs[0]), temp_work.join(name=f"{pmid}.pdf").as_posix())
                            localized = True
                            source = "PMC"
                    except Exception:
                        pass

            if not localized:
                abstract = get_abstract(pmid, prepend_title=True)
                if abstract:
                    with open(txt_archive.join(name=f"{pmid}.txt"), "w", encoding="utf-8") as f:
                        f.write(abstract)
                    localized = True
                    source = "ABS"

            if localized:
                if source == "PMC":
                    pdf_file = temp_work.join(name=f"{pmid}.pdf")
                    reader = PdfReader(pdf_file)
                    text = "\n".join(page.extract_text() for page in reader.pages)
                    txt_archive.join(name=f"{pmid}.txt").write_text(text, encoding="utf-8")
                    shutil.move(pdf_file.as_posix(),
                                pdf_archive.join(name=pdf_file.name).as_posix())
                logger.info(f"{pmid} ({source}) - OK")
            else:
                logger.info(f"{pmid} - NO CONTENT")

        except Exception as e:
            logger.info(f"[{pmid} - FAILED: {e}")


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

    statuses = Counter(r["status"] for r in stats)

    logger.info(f"Extraction complete: {statuses['ok']} new, {statuses['skipped']} "
                f"skipped, {statuses['missing_text']} missing text, "
                f"{len(statuses) - statuses['ok'] - statuses['skipped'] - statuses['missing_text']} errors")
    if statuses.get('completed'):
        total_out = sum(r["output_tokens"] for r in stats if r["status"] == "completed")
        logger.info(f"Avg output tokens/paper: {total_out // statuses['completed']}")

    csv_path = pystow.module("indra", "cogex", "clinical_trial_results").base / "extraction_stats.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pmid", "status", "input_tokens", "output_tokens"])
        writer.writeheader()
        writer.writerows(stats)
    logger.info(f"Stats saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000,
                        help="Max PMIDs to process (default: 1000)")
    args = parser.parse_args()

    pmids_path = pystow.join("indra", "cogex", "clinical_trial_results",
                             name="intersection_pmids.txt")

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

    download_texts(pmids)
    run_extraction(pmids)


if __name__ == "__main__":
    main()
