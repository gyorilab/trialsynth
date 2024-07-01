"""Gets WHO data from REST API (not implemented) or saved file"""

import logging
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


def get_api_data() -> None:
    raise NotImplementedError("WHO CSV data fetch not automated")

    # How to get the dump:
    #
    # Navigate to
    # https://worldhealthorg-my.sharepoint.com/:f:/g/personal/karamg_who_int/Eg8Fm2P5H7lCnJjDZaVLXcQBsBgP3tYXdMQITaidjK05uw?id=%2fpersonal%2fkaramg_who_int%2fDocuments%2fICTRP+weekly+updates&xsdata=MDV8MDJ8b2dhLnRAbm9ydGhlYXN0ZXJuLmVkdXw1YzE4NzVjNDI5NDk0MzQwNDZiMTA4ZGM5MWJmNDEzZHxhOGVlYzI4MWFhYTM0ZGFlYWM5YjlhMzk4YjkyMTVlN3wwfDB8NjM4NTQ1NDk3ODYxNzQyMzQzfFVua25vd258VFdGcGJHWnNiM2Q4ZXlKV0lqb2lNQzR3TGpBd01EQWlMQ0pRSWpvaVYybHVNeklpTENKQlRpSTZJazFoYVd3aUxDSlhWQ0k2TW4wPXwwfHx8&sdata=UndvcUZmbitCNEZLRDhkVUo3NEFjTWswNmNTMnd1ZnFxMEdsWXBnUWNkTT0%3d
    #
    # Select most recent dump (e.g. "ICTRP_FullExport-1003291-20-06-2024") and press 'Download'
    # Save the export to the trial_synth/who/data directory as 'ICTRP.csv'


def load_saved_pickled_data(path: Path) -> pd.DataFrame:
    """Loads the pickled data from a saved file

    Parameters
    ----------
    path : Path
        Path to the saved pickled data

    Returns
    -------
    DataFrame
        The pickled data
    """
    logger.debug(f"Loading pickled WHO data from {path}")
    try:
        return pd.read_pickle(path)
    except Exception:
        logger.exception(f"Could not load pickled data from {path}")