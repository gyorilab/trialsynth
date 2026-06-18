"""
Orchestrator: intersection PMIDs -> text download -> anchor extraction ->
grounded JSONs.

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
import pickle
import argparse
from collections import Counter

import tqdm
import pystow
from openai import OpenAI
from indra.literature.pmc_client import id_lookup, get_text_s3
from indra.literature.pubmed_client import get_abstract

from trialsynth.base.extract.extract import process_pmid
from trialsynth.base.extract.paths import CLINICALTRIALS_DIR, \
    RESULTS_RAW_DIR, RESULTS_DIR

output_dir = pystow.module("trialsynth", "results", "raw")
txt_archive = pystow.module("trialsynth", "content", "txt")
trial_pkl_path = CLINICALTRIALS_DIR / "clinicaltrials.pkl.gz"
pubmed_nct_links_path = CLINICALTRIALS_DIR / "pubmed_nct_links.csv"

logger = logging.getLogger('trialsynth.base.extract.orchestrate')


def get_intersection_pmids(limit: int = None) -> list[str]:
    """Return intersection PMIDs (registry RESULT links intersect PubMed scan),
    up to `limit`."""

    logger.info("Loading registry result links...")
    registry_result_links = set()
    with gzip.open(trial_pkl_path, "rb") as f:
        trials = pickle.load(f)
    for trial in trials:
        if trial.references:
            for ref in trial.references:
                pmid = ref[0] if isinstance(ref, (tuple, list)) else ref
                ref_type = (
                    str(ref[1]).upper()
                    if isinstance(ref, (tuple, list)) and len(ref) > 1
                    else ""
                )
                if pmid and "RESULT" in ref_type:
                    registry_result_links.add(pmid)

    logger.info("Loading PubMed scan links...")
    pubmed_pmids = set()
    with open(pubmed_nct_links_path, "r") as f:
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


def download_texts(pmids: list[str]):
    logger.info(f"Downloading text for {len(pmids)} PMIDs...")

    for pmid in tqdm.tqdm(pmids):
        if txt_archive.join(name=f"{pmid}.txt").exists():
            continue

        try:
            text = None
            source = ""

            pmcid = id_lookup(pmid, idtype="pmid").get("pmcid")
            if pmcid:
                text = get_text_s3(pmcid)
                if text:
                    source = f"PMC-S3:{pmcid}"

            if not text:
                text = get_abstract(pmid, prepend_title=True)
                if text:
                    source = "ABS"

            if text:
                txt_archive.join(name=f"{pmid}.txt").write_text(text, encoding="utf-8")
                logger.info(f"{pmid} ({source}) - OK")
            else:
                logger.info(f"{pmid} - NO CONTENT")

        except Exception as e:
            logger.info(f"{pmid} - FAILED: {e}")


def run_extraction(pmids: list[str]):
    logger.info(f"Running anchor extraction on {len(pmids)} PMIDs...")
    client = OpenAI()
    stats = []

    for pmid in pmids:
        row = process_pmid(pmid, client, txt_archive.base, output_dir.base)
        stats.append(row)
        if row["status"] == "ok":
            logger.info(f"  {pmid} extracted ({row['output_tokens']} output tokens)")
        elif row["status"] == "skipped":
            logger.info(f"  {pmid} skipped (already exists)")
        else:
            logger.warning(f"  {pmid} -> {row['status']}")

    statuses = Counter(r["status"] for r in stats)

    n_errors = (
        len(statuses) - statuses['ok'] - statuses['skipped'] - statuses['missing_text']
    )
    logger.info(
        f"Extraction complete: {statuses['ok']} new, {statuses['skipped']} skipped, "
        f"{statuses['missing_text']} missing text, {n_errors} errors"
    )
    if statuses.get('completed'):
        total_out = sum(r["output_tokens"] for r in stats if r["status"] == "completed")
        logger.info(f"Avg output tokens/paper: {total_out // statuses['completed']}")

    csv_path = RESULTS_DIR.join(name="extraction_stats.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["pmid", "status", "input_tokens", "output_tokens"]
        )
        writer.writeheader()
        writer.writerows(stats)
    logger.info(f"Stats saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000,
                        help="Max PMIDs to process (default: 1000)")
    args = parser.parse_args()

    pmids_path = RESULTS_DIR.join(name="intersection_pmids.txt")

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
