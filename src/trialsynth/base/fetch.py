import logging
from pathlib import Path

import pandas as pd
import requests
from tqdm import trange
from typing import Optional

from .config import BaseConfig
from .models import Trial
import pickle
logger = logging.getLogger(__name__)


class BaseFetcher:
    def __init__(self, url: str = '', api_parameters: dict = None):
        self.raw_data: list[Trial] = list()
        self.url = url
        self.api_parameters = api_parameters

        self.config: BaseConfig = None

    def get_api_data(self) -> None:
        """
        Fetches data from an API, and transforms it into a list of `Trial`s
        Parameters
        ----------
        url : str
            URL of the API endpoint
        request_parameters: dict
            Parameters to send with API request
        """
        raise NotImplementedError("Must be defined in subclass.")

    def send_request(self) -> dict:
        """ Sends a request to the API and returns the response as JSON

        Returns
        -------
        dict
            JSON response from API
        """
        try:
            response = requests.get(self.url, self.params)
            return response.json()
        except Exception:
            logger.exception(f"Error with request to {self.url} using params {self.params}")
            raise

    def load_saved_data(self):
        path = self.config.raw_data_path
        logger.info(f"Loading {self.config.registry} data from {path}")

        try:
            self.raw_data = pickle.load(path)
        except Exception:
            logger.exception(f"Could not load data from {path}")
