"""Code for extracting NCT IDs from pubmed XML files

Creates PMID -> NCT ID relations from the PubMed XML baseline archive.

Output: pubmed_nct_links.tsv.gz
Format: TSV with columns PMID and NCT_ID, compressed with gzip.
"""
import csv
import gzip
import logging
import os
from pathlib import Path

import click
from lxml import etree
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

from indra.literature import pubmed_client
from trialsynth.base.extract.paths import CLINICALTRIALS_DIR, XML_DIR


PMID_NCT_LINKS = CLINICALTRIALS_DIR.join(name="pubmed_nct_links.tsv.gz")


logger = logging.getLogger('trialsynth.base.extract.build_pubmed_nct_links')


def _process_one_xml_file(xml_file: Path) -> list[tuple[str, str]]:
    import tqdm as tqdm_module

    os.environ["TQDM_DISABLE"] = "1"
    # TQDM_DISABLE is read at tqdm import time; patch in worker to silence inner bars.
    tqdm_module.tqdm = lambda iterable, *args, **kwargs: iterable

    tree = etree.parse(xml_file)
    nct_ids_by_pmid = pubmed_client.get_nct_ids_from_full_xml(tree)
    return [
        (pmid, nct_id)
        for pmid, nct_ids in nct_ids_by_pmid.items()
        for nct_id in nct_ids
    ]


def _pubmed_trial_links(
    xml_directory: Path | str,
    download_missing: bool,
    max_files: int | None = None,
    max_workers: int = 8,
) -> set[tuple[str, str]]:
    xml_directory = Path(xml_directory)
    xml_files = list(xml_directory.glob("pubmed*.xml.gz"))
    if not xml_files or download_missing:
        pubmed_client.ensure_xml_files(xml_directory.as_posix())

    xml_files = sorted(xml_directory.glob("pubmed*.xml.gz"))
    if max_files is not None:
        xml_files = xml_files[:max_files]

    logger.info(f"Found {len(xml_files)} XML files to process.")

    pair_lists = process_map(
        _process_one_xml_file,
        xml_files,
        chunksize=20,
        desc="Processing XML files",
        unit="file",
        max_workers=min(max_workers, os.cpu_count() or 1),
    )
    trial_relations: set[tuple[str, str]] = set()
    for pairs in pair_lists:
        trial_relations.update(pairs)
    return trial_relations


def generate_pubmed_trial_links(
    xml_directory: Path | str = XML_DIR.base,
    download_missing: bool = False,
    reprocess: bool = False,
    max_files: int | None = None,
    max_workers: int = 8,
):
    """Downloads, finds, and caches NCT IDs from PubMed XML files

    Parameters
    ----------
    xml_directory :
        Path to the directory containing PubMed XML files.
    download_missing :
        If true, download missing PubMed XML files. Default: False.
    reprocess :
        If true, reprocess the PubMed XML files even if the NCT IDs are already
        cached in PMID_NCT_LINKS. This will overwrite the existing
        PMID_NCT_LINKS TSV file. Default: False.
    max_files :
        If set, only process this many XML files (for testing).
    max_workers :
        Maximum number of worker processes to use for parallel processing.
        Default: 8.
    """
    if not reprocess and PMID_NCT_LINKS.exists():
        logger.info(f"PubMed NCT links already processed, skipping. Use --reprocess to overwrite.")
        return
    trial_relations = sorted(
        _pubmed_trial_links(
            xml_directory=xml_directory,
            download_missing=download_missing,
            max_files=max_files,
            max_workers=max_workers,
        )
    )

    chunk_size = 10000

    logger.info(
        f"Writing {len(trial_relations)} (PMID, NCT_ID) pairs to {PMID_NCT_LINKS}..."
    )
    with gzip.open(PMID_NCT_LINKS, "wt") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["PMID", "NCT_ID"])
        for i in tqdm(range(0, len(trial_relations), chunk_size), desc="Writing TSV", unit="chunk"):
            chunk = trial_relations[i : i + chunk_size]
            writer.writerows(chunk)


@click.command()
@click.option(
    "--download-missing/--no-download-missing",
    default=True,
    show_default=True,
    help="Download missing PubMed XML baseline/update files before parsing.",
)
@click.option(
    "--reprocess/--no-reprocess",
    default=False,
    show_default=True,
    help="Reprocess the PubMed XML files even if the NCT IDs are already cached in PMID_NCT_LINKS.",
)
@click.option(
    "--xml-directory",
    type=click.Path(path_type=Path, file_okay=False),
    default=XML_DIR.base,
    show_default=True,
    help="Directory containing PubMed XML .xml.gz files.",
)
@click.option(
    "--max-files",
    type=int,
    default=None,
    help="Max total XML files on disk to use (cached + newly downloaded; for testing).",
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    help="Maximum number of worker processes to use for parallel processing.",
)
def main(
    download_missing: bool,
    reprocess: bool,
    xml_directory: Path,
    max_files: int | None,
    max_workers: int,
) -> None:
    generate_pubmed_trial_links(
        reprocess=reprocess,
        xml_directory=xml_directory,
        download_missing=download_missing,
        max_files=max_files,
        max_workers=max_workers,
    )


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    main()
