"""
Retained for historical record; not part of the active trialsynth pipeline.

Extract PMID -> NCT ID links from the PubMed XML baseline archive.

NCT IDs are sourced from:
  - DataBank blocks where DataBankName = "ClinicalTrials.gov"
  - AbstractText free-text mentions (regex NCT\d{8})

Output: pubmed_nct_links.csv saved to trialsynth/clinicaltrials/ via pystow.
Checkpoint: processed_files.txt in the same directory for safe resume.

Usage:
    python build_pubmed_nct_links.py --archive /path/to/xml_archive.tar
    python build_pubmed_nct_links.py --archive /path/to/xml_archive.tar --threads 8
    python build_pubmed_nct_links.py --archive /path/to/xml_archive.tar --limit 10
"""

import argparse
import csv
import gzip
import io
import logging
import re
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pystow
import tqdm

logger = logging.getLogger('trialsynth.base.extract.build_pubmed_nct_links')

PMID_RE = re.compile(r'<PMID[^>]*>(\d+)</PMID>')
DATABANK_BLOCK_RE = re.compile(r'<DataBank>(.*?)</DataBank>', re.DOTALL)
DATABANK_NAME_RE = re.compile(r'<DataBankName>ClinicalTrials\.gov</DataBankName>')
ACCESSION_RE = re.compile(r'<AccessionNumber>(NCT\d{8})</AccessionNumber>')
ABSTRACT_RE = re.compile(r'<AbstractText[^>]*>(.*?)</AbstractText>', re.DOTALL)
NCT_RE = re.compile(r'NCT\d{8}')

TOTAL_FILES = 1613  # number of .xml.gz files in the PubMed 2025 baseline archive


def parse_member(data: bytes) -> list[tuple[str, str]]:
    """Parse a gzipped PubMed XML file via regex and return (pmid, nct_id) pairs."""
    with gzip.open(io.BytesIO(data)) as gz:
        text = gz.read().decode('utf-8', errors='replace')

    rows = []
    for article in text.split('<PubmedArticle>')[1:]:
        pmid_match = PMID_RE.search(article)
        if not pmid_match:
            continue
        pmid = pmid_match.group(1)

        nct_ids = set()

        # Structured: DataBank blocks for ClinicalTrials.gov
        for block in DATABANK_BLOCK_RE.finditer(article):
            block_text = block.group(1)
            if DATABANK_NAME_RE.search(block_text):
                for acc in ACCESSION_RE.finditer(block_text):
                    nct_ids.add(acc.group(1))

        # Free-text: regex over AbstractText only
        for abstract in ABSTRACT_RE.finditer(article):
            nct_ids.update(NCT_RE.findall(abstract.group(1)))

        for nct_id in nct_ids:
            rows.append((pmid, nct_id))

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True,
                        help='Path to xml_archive.tar')
    parser.add_argument('--threads', type=int, default=8,
                        help='Number of worker threads (default: 8)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Process only first N files (for testing)')
    args = parser.parse_args()

    output_path = pystow.join("trialsynth", "clinicaltrials", name="pubmed_nct_links.csv")
    checkpoint_path = pystow.join("trialsynth", "clinicaltrials", name="processed_files.txt")

    done = set()
    if checkpoint_path.exists():
        done = set(checkpoint_path.read_text(encoding='utf-8').splitlines())
        logger.info(f"Resuming: {len(done)} files already processed.")

    csv_exists = output_path.exists()
    total = (args.limit or TOTAL_FILES) - len(done)
    logger.info(f"~{total} files to process, {len(done)} skipped.")

    write_lock = threading.Lock()
    total_links = 0

    sem = threading.Semaphore(args.threads * 2)

    with open(output_path, 'a', newline='', encoding='utf-8') as csv_file, \
         open(checkpoint_path, 'a', encoding='utf-8') as ckpt_file, \
         tqdm.tqdm(total=total, desc='Parsing', unit='file') as pbar:

        writer = csv.writer(csv_file)
        if not csv_exists:
            writer.writerow(['pmid', 'nct_id'])

        def process(name: str, data: bytes) -> None:
            try:
                rows = parse_member(data)
                with write_lock:
                    writer.writerows(rows)
                    csv_file.flush()
                    ckpt_file.write(name + '\n')
                    ckpt_file.flush()
                    nonlocal total_links
                    total_links += len(rows)
                    pbar.update(1)
                    pbar.set_postfix(links=total_links)
                    logger.info(f"[{pbar.n}/{total}] {name} -> {len(rows)} links")
            except Exception as e:
                logger.error(f"Failed {name}: {e}")
            finally:
                sem.release()

        processed = 0
        with tarfile.open(args.archive, 'r:') as tar, \
             ThreadPoolExecutor(max_workers=args.threads) as executor:

            for member in tar:
                if not member.name.endswith('.xml.gz'):
                    continue
                if member.name in done:
                    continue
                if args.limit and processed >= args.limit:
                    break

                sem.acquire()
                data = tar.extractfile(member).read()
                executor.submit(process, member.name, data)
                processed += 1

    logger.info(f"Done. {total_links} links written to {output_path}.")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    main()
