from collections import defaultdict
import logging

from tqdm import tqdm

from .config import Config
from .fetch import Fetcher, load_saved_data
from .store import Storer
from .transform import Transformer
from .validate import validate_node_data, validate_edge_data


logger = logging.getLogger(__name__)


class Processor:
    """Processes Clinicaltrials.gov data using Config, Fetcher, Storer, and Transformer objects.

    Attributes
    ----------
    config : Config
        User-mutable properties of Clinicaltrials.gov data processing
    fetcher : Fetcher
        Fetches Clinicaltrials.gov data from the REST API or a saved file
    storer : Storer
        Stores processed data to disk
    transformer : Transformer
        Transforms raw data into nodes and edges for a graph database
    node_iterator : method
        Method to generate nodes from the transformed data
    nodes_by_type : defaultdict
        Nodes grouped by type
    edges : set
        Edges between nodes

    Parameters
    ----------
    config : Config
        User-mutable properties of Clinicaltrials.gov data processing
    fetcher : Fetcher
        Fetches Clinicaltrials.gov data from the REST API or a saved file
    storer : Storer
        Stores processed data to disk
    transformer : Transformer
        Transforms raw data into nodes and edges for a graph database
    """

    def __init__(
        self,
        config: Config,
        fetcher: Fetcher,
        storer: Storer,
        transformer: Transformer,
    ):
        self.config = config
        self.fetcher = fetcher
        self.storer = storer
        self.transformer = transformer

        self.node_iterator = self.transformer.get_nodes
        self.nodes_by_type = defaultdict(list)
        self.edges = set()

    def ensure_api_response_data_saved(self, refresh: bool = False) -> None:
        """Ensures that the input data exists on disk, either by fetching from the API or loading from a saved file

        Parameters
        ----------
        refresh : bool
            Whether to fetch data from the API even if it exists on disk. Default: False
        """
        logger.debug("Ensuring input data exists on disk")
        if self.config.unprocessed_file_path.is_file() and not refresh:
            self.fetcher.raw_data = load_saved_data(self.config.unprocessed_file_path)
        else:
            self.fetcher.get_api_data(self.config.api_url, self.config.api_parameters)
            self.storer.save_data(self.fetcher.raw_data, self.config.unprocessed_file_path)

    def clean_and_transform_data(self) -> None:
        """Cleans and transforms the raw data into nodes and edges."""
        logger.debug("Cleaning and transforming data")
        self.transformer.df = self.fetcher.raw_data
        self.transformer.clean_data_values()

    def set_nodes_and_edges(self) -> None:
        """Sets nodes and edges from the transformed data."""
        self.set_nodes_by_type()
        self.set_edges()

    def set_nodes_by_type(self) -> None:
        """Sets nodes grouped by type using the node iterator."""
        logger.debug("Setting nodes by type")
        nodes = tqdm(
            self.node_iterator(),
            desc="Node generation",
            unit_scale=True,
            unit="node"
        )

        for ix, node in enumerate(nodes):
            self.nodes_by_type[node["labels"][0]].append(node)

    def set_edges(self) -> None:
        """Sets edges from the transformed data.

        Raises
        ------
        RuntimeError
            If no relations were generated for the graph
        """
        logger.debug("Setting edges")
        self.edges = list(self.transformer.get_edges())
        if len(self.edges) == 0:
            raise RuntimeError(f"No relations were generated for {self.name}")

    def validate_data(self) -> None:
        """Validates the graph data for consistency."""
        logger.debug("Validating graph data")
        for nodes in self.nodes_by_type.values():
            validate_node_data(self.config.name, nodes)
        validate_edge_data(self.config.name, self.edges)

    def save_graph_data(self) -> None:
        """Saves the output data to disk using the storer."""
        logger.debug("Saving output data")
        self.storer.save_node_data()
        self.storer.save_edge_data(self.edges)
