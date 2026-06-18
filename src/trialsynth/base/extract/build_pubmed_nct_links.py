"""
Code for extracting NCT IDs from pubmed XML files

Creates PMID -> NCT ID relations from the PubMed XML baseline archive.

Output: pubmed_nct_links.tsv.gz

# todo: long term plan:
Duplicate code for now, with a plan to refactor this code (together with similar
code in CoGex and INDRA DB) into INDRA, which has similar code.
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


PMID_NCT_LINKS = CLINICALTRIALS_DIR / "pubmed_nct_links.tsv.gz"


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
        desc="Processing XML files",
        unit="file",
        max_workers=min(16, os.cpu_count() or 1),
    )
    trial_relations: set[tuple[str, str]] = set()
    for pairs in pair_lists:
        trial_relations.update(pairs)
    return trial_relations


def generate_pubmed_trial_links(
    xml_directory: Path | str = XML_DIR,
    download_missing: bool = False,
    max_files: int | None = None,
):
    """Downloads, finds, and caches NCT IDs from PubMed XML files

    Parameters
    ----------
    xml_directory :
        Path to the directory containing PubMed XML files.
    download_missing :
        If true, download missing PubMed XML files. Default: False.
    max_files :
        If set, only process this many XML files (for testing).
    """
    trial_relations = sorted(
        _pubmed_trial_links(
            xml_directory=xml_directory,
            download_missing=download_missing,
            max_files=max_files,
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
    "--xml-directory",
    type=click.Path(path_type=Path, file_okay=False),
    default=XML_DIR,
    show_default=True,
    help="Directory containing PubMed XML .xml.gz files.",
)
@click.option(
    "--max-files",
    type=int,
    default=None,
    help="Max total XML files on disk to use (cached + newly downloaded; for testing).",
)
def main(
    download_missing: bool,
    xml_directory: Path,
    max_files: int | None,
) -> None:
    generate_pubmed_trial_links(
        xml_directory=xml_directory,
        download_missing=download_missing,
        max_files=max_files,
    )


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    main()
