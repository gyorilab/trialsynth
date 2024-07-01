import logging

import click

from .config import Config, DATA_DIR, SAMPLE_DIR
from .fetch import Fetcher
from .store import Storer
from .transform import Transformer
from .process import Processor
from .util import ensure_output_directory_exists


logger = logging.getLogger(__name__)


@click.command()
def main():
    click.secho("Processing clincaltrials.gov data", fg="green", bold=True)
    ensure_output_directory_exists()
    ensure_output_directory_exists(path=SAMPLE_DIR)
    config = Config()
    fetcher = Fetcher(
        url=config.api_url,
        request_parameters=config.api_parameters
    )
    transformer = Transformer()
    storer = Storer(
        node_iterator=transformer.get_nodes,
        node_types=config.node_types,
        data_directory=DATA_DIR,
        sample_directory=SAMPLE_DIR
    )
    clinical_trials_processor = Processor(
        config=config,
        fetcher=fetcher,
        storer=storer,
        transformer=transformer
    )
    clinical_trials_processor.ensure_api_response_data_saved()
    clinical_trials_processor.clean_and_transform_data()
    clinical_trials_processor.set_nodes_and_edges()
    clinical_trials_processor.validate_data()
    clinical_trials_processor.save_graph_data()


if __name__ == "__main__":
    main()
