import csv
import gzip
import logging
from pathlib import Path
from typing import Iterable, Optional

from tqdm import tqdm

logger = logging.getLogger(__name__)


def save_data_as_flatfile(
    rows: list[Iterable],
    path: Path,
    headers: list[str],
    sample_path: Optional[Path] = None,
    num_samples: Optional[int] = None,
) -> None:
    """Saves data to disk as compressed TSV

    Parameters
    ----------
    rows : list[Iterable]
        Data to save
    path : Path
        The path where data is stored
    headers : list[str]
        The headers of the data
    sample_path : Optional[Path]
        The path where sample data is stored
    num_samples : Optional[int]
        The number of sample entries to store
    """
    chunk_size = 1000
    with gzip.open(path, mode="wt") as file:
        data_writer = csv.writer(file, delimiter="\t")
        data_writer.writerow(headers)
        if sample_path and num_samples:
            with sample_path.open("wt") as sample:
                sample_writer = csv.writer(sample, delimiter="\t")
                sample_writer.writerow(headers)
                for _, row in zip(range(num_samples), rows):
                    sample_writer.writerow(row)

        data_length = len(rows)
        with tqdm(
            total=data_length, desc="Writing data to file", unit="row", unit_scale=True
        ) as pbar:
            for i in range(0, data_length, chunk_size):
                data_writer.writerows(rows[i : i + chunk_size])
                pbar.update(chunk_size)
