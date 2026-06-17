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
from collections.abc import Iterator
from pathlib import Path

import click
from lxml import etree
from tqdm import tqdm

from indra.literature import pubmed_client
from trialsynth.base.extract.paths import CLINICALTRIALS_DIR, XML_DIR


PMID_NCT_LINKS = CLINICALTRIALS_DIR / "pubmed_nct_links.tsv.gz"


logger = logging.getLogger('trialsynth.base.extract.build_pubmed_nct_links')


def generate_pubmed_trial_links(
    xml_directory: Path | str,
    download_missing: bool = False,
    max_pairs: int | None = None,
    max_files: int | None = None,
) -> Iterator[tuple[str, str]]:
    xml_directory = Path(xml_directory)
    xml_files = list(xml_directory.glob("pubmed*.xml.gz"))
    if not xml_files or download_missing:
        pubmed_client.ensure_xml_files(xml_directory.as_posix())

    xml_files = sorted(xml_directory.glob("pubmed*.xml.gz"))
    if max_files is not None:
        xml_files = xml_files[:max_files]

    logger.info(f"Found {len(xml_files)} XML files to process.")

    trial_relations = set()
    for xml_file in tqdm(xml_files, desc="Processing XML files", unit="file"):
        tree = etree.parse(xml_file)
        nct_ids_by_pmid = pubmed_client.get_nct_ids_from_full_xml(tree)
        for pmid, nct_ids in nct_ids_by_pmid.items():
            for nct_id in nct_ids:
                if (pmid, nct_id) not in trial_relations:
                    yield (pmid, nct_id)
                    trial_relations.add((pmid, nct_id))
                    if max_pairs is not None and len(trial_relations) >= max_pairs:
                        return


@click.command()
@click.option(
    "--download-missing/--no-download-missing",
    default=True,
    show_default=True,
    help="Download missing PubMed XML baseline/update files before parsing.",
)
@click.option(
    "--max-pairs",
    type=int,
    default=None,
    help="Stop after generating this many unique (PMID, NCT_ID) pairs (for testing).",
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
    max_pairs: int | None,
    xml_directory: Path,
    max_files: int | None,
) -> None:
    trial_relations = sorted(
        generate_pubmed_trial_links(
            xml_directory=xml_directory,
            download_missing=download_missing,
            max_pairs=max_pairs,
            max_files=max_files,
        )
    )

    chunk_size = 100000

    logger.info(
        f"Writing {len(trial_relations)} (PMID, NCT_ID) pairs to {PMID_NCT_LINKS}..."
    )
    with gzip.open(PMID_NCT_LINKS, "wt") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["PMID", "NCT_ID"])
        for i in tqdm(range(0, len(trial_relations), chunk_size), desc="Writing TSV", unit="chunk"):
            chunk = trial_relations[i : i + chunk_size]
            writer.writerows(chunk)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    main()
