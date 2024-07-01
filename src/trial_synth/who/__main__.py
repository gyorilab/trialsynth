"""
Extract clinical trial information from the WHO.

Run with `python -m trial_synth.who`
"""

import logging

import click
import pandas as pd

from .config import Config
from .process import Processor
from .store import store_dataframe_as_flat_file
from .util import ensure_output_directory_exists
from .transform import ensure_df

CONFIG = Config()
logger = logging.getLogger(__name__)


@click.command()
def main():
    click.secho("Processing WHO ICTRP data", fg="green", bold=True)
    ensure_output_directory_exists(CONFIG.data_dir_path)
    ensure_output_directory_exists(CONFIG.sample_dir_path)
    ensure_output_directory_exists(CONFIG.ner_dir_path)
    df = ensure_df()
    store_dataframe_as_flat_file(df, CONFIG.sample_path, "\t", False)
    processor = Processor(df, CONFIG)
    processor.process_who_data()


if __name__ == "__main__":
    main()
