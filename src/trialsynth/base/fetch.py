import gzip
import logging
import pickle

import requests

from .config import Config
from .models import Trial
from .util import must_override

logger = logging.getLogger(__name__)


class Fetcher:
    """Base class for fetching data from an API and transforming it into a list of :class:`Trial` objects

    Attributes
    ----------
    raw_data : list[Trial]
        Raw data from the API
    url : str
        URL of the API endpoint
    api_parameters : dict
        Parameters to send with the API request
    config : Config
        User-mutable properties of registry data processing

    Parameters
    ----------
    config : Config
        User-mutable properties of registry data processing
    """

    def __init__(self, config: Config):
        self.config: Config = config
        self.raw_data: list[Trial] = list()
        self.url: str = config.api_url
        self.api_parameters: dict = {}

    @must_override
    def get_api_data(self, reload: bool = False) -> None:
        """Fetches data from the API, and transforms it into a list of :class:`Trial` objects

        Parameters
        ----------
        reload : bool
            Whether to reload the data from the API
        """
        pass

    def save_raw_data(self):
        """Pickles raw trial data as a list of :class:`Trial` objects to disk"""
        logger.info(f"Pickling raw trial data to {self.config.raw_data_path}")
        with gzip.open(self.config.raw_data_path, "wb") as file:
            pickle.dump(self.raw_data, file)

    def send_request(self) -> dict:
        """Sends a request to the API and returns the response as JSON

        Returns
        -------
        dict
            JSON response from API
        """
        try:
            response = requests.get(self.url, self.api_parameters, timeout=10)
            return response.json()
        except Exception:
            logger.exception(
                f"Error with request to {self.url} using params {self.api_parameters}"
            )
            raise

    def load_saved_data(self) -> None:
        """Load saved data as a list of :class:`Trial` objects from disk"""
        logger.info(
            f"Loading saved data from {self.config.raw_data_path}. This may take a bit."
        )
        with gzip.open(self.config.raw_data_path, "r") as file:
            self.raw_data = pickle.load(file)
