import os

import pytest
from pydantic import ValidationError

from trialsynth.clinical_trials_dot_gov import config, fetch

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
