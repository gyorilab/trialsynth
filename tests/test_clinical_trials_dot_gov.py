import os

import pytest
import tempfile
from pydantic import ValidationError

from trialsynth.clinical_trials_dot_gov import config, fetch, process

DOCKERIZED = os.environ.get("DOCKERIZED", False)


@pytest.mark.skipif(DOCKERIZED, reason="Test against API, not stub")
def test_stability():
    """
    If the structure of the API response changes it will break the pipeline.
    Get sample data from the live API and validate it using its data model.
    """

    configuration = config.CTConfig()
    try:
        fetch.CTFetcher(configuration)._read_next_page()
    except ValidationError as exc:
        pytest.fail(f"Unexpected error while flattening API response data: {exc}")


def test_end_to_end():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["DATA_DIR"] = temp_dir
        configuration = config.CTConfig()
        processor = process.CTProcessor(
            reload_api_data=True,
            store_samples=False,
            validate=False,
        )
        processor.run(max_pages=1)
        assert all(
            p.exists() for p in [
                configuration.raw_data_path,
                configuration.trials_path,
                configuration.edges_path,
                configuration.bio_entities_path
            ]
        ), "Not all expected files were created in the temporary directory."

        # Check that the files are not empty
        assert os.path.getsize(configuration.raw_data_path) > 0, "Raw data file is empty."
        assert os.path.getsize(configuration.trials_path) > 0, "Trials file is empty."
        assert os.path.getsize(configuration.edges_path) > 0, "Edges file is empty."
        assert os.path.getsize(configuration.bio_entities_path) > 0, "Bio entities file is empty."
