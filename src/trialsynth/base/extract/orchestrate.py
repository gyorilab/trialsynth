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
import argparse
from collections import Counter

import tqdm
from openai import OpenAI
from indra.literature.pmc_client import id_lookup, get_text_s3
from indra.literature.pubmed_client import get_abstract

from trialsynth.ctgov.config import CTConfig
from trialsynth.base.extract.extract import process_pmid
from trialsynth.base.extract.paths import RESULTS_RAW_DIR, RESULTS_DIR, \
    CONTENT_TXT_DIR


logger = logging.getLogger('trialsynth.base.extract.orchestrate')


def get_intersection_pmids(limit: int = None) -> list[str]:
    """Return PMIDs defined from the output of

    Parameters
    ----------
    limit :
        Optional limit on the number of PMIDs to return. If None, return all.

    Returns
    -------
    :
        List of PMIDs that are in both the registry result links and the PubMed
        scan links.
    """

    ct_config = CTConfig()
    if not ct_config.trial_publication_edges_path.exists():
        raise FileNotFoundError(
            f"Trial-publication edges file not found: "
            f"{ct_config.trial_publication_edges_path}. Must run clinicaltrials "
            f"pipeline before running this script."
        )
    with gzip.open(ct_config.trial_publication_edges_path, "rt") as f:
        reader = csv.reader(f)
        _ = next(reader)
        intersection = {
            row[1] for row in reader if row[1]
        }

    return sorted(intersection)[:limit] if limit else sorted(intersection)


def download_texts(pmids: list[str]):
    logger.info(f"Downloading text for {len(pmids)} PMIDs...")

    for pmid in tqdm.tqdm(pmids):
        if CONTENT_TXT_DIR.join(name=f"{pmid}.txt").exists():
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
                CONTENT_TXT_DIR.join(name=f"{pmid}.txt").write_text(text, encoding="utf-8")
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
        row = process_pmid(pmid, client, CONTENT_TXT_DIR.base, RESULTS_RAW_DIR.base)
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
