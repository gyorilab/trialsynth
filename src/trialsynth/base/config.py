import logging
import os
import shutil
from configparser import RawConfigParser
from pathlib import Path
from typing import Dict, Optional, Union, Any
from trialsynth.base.resources import DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)


HOME_DIR = Path(os.path.expanduser("~"))


class TrialSynthConfigError(Exception):
    pass


def parse_config(registry_name: str, config_path: str | Path) -> dict[str, Any]:
    config_dict = {}
    parser = RawConfigParser()
    parser.optionxform = lambda x: x
    parser.read(config_path)
    sections = parser.sections()

    options = parser.options("trialsynth")
    for option in options:
        config_dict[option] = str(parser.get("trialsynth", option))

    if registry_name not in sections:
        raise ValueError(
            f"Registry [{registry_name}] not found in configuration file."
        )

    options = parser.options(registry_name)
    for option in options:
        if option in config_dict:
            logger.info(
                "Overwriting package level configuration with registry level for option: "
                + option
            )
        config_dict[option] = str(parser.get(registry_name, option))
    return config_dict


class Config:
    """User-mutable properties of a registry for data processing.

    Parameters
    ----------
    registry : str
        The name of the registry for which the configuration is being created.

    Attributes
    ----------
    registry : str
        The name of the registry for which the configuration is being created.
    config_dict : dict
        The configuration dictionary.
    data_dir : Path
        The directory where the data is stored.
    sample_dir : Path
        The directory where the samples are stored.
    raw_data_path : Path
        The path to the raw data file stored as a list of :class:`Trial` objects.
    edges_path : Path
        The path to the edges file stored as a compressed TSV file.
    edges_sample_path : Path
        The path to the sample edges file stored as a TSV file.
    bio_entities_path : Path
        The path to the bioentity nodes file stored as a compressed TSV file.
    bio_entities_sample_path : Path
        The path to the sample bioentity nodes file stored as a TSV file.
    trials_path : Path
        The path to the trial nodes file stored as a compressed TSV file.
    trials_sample_path : Path
        The path to the sample trial nodes file stored as a TSV file.
    num_sample_entries : int
        The number of sample entries to store.
    api_url : str
        The URL of the API endpoint.
    api_parameters : dict
        The parameters to send with the API request.
    """

    def __init__(self, registry: str):
        self.registry: str = registry
        self.config_dict: dict = self._create_config_dict()

        # directories
        self.data_dir: Path = Path(self.get_config("DATA_DIR"))
        self.sample_dir: Path = self.data_dir.joinpath("samples")

        # file paths
        self.raw_data_path: Path = self.get_data_path(self.get_config("RAW_TRIAL_DATA"))

        self.edges_path: Path = self.get_data_path(self.get_config("EDGES_FILE"))
        self.edges_sample_path: Path = self.get_sample_path(
            self.get_config("EDGES_SAMPLE_FILE")
        )

        self.bio_entities_path = self.get_data_path(
            self.get_config("BIOENTITY_NODES_FILE")
        )
        self.bio_entities_sample_path = self.get_sample_path(
            self.get_config("BIOENTITY_SAMPLE_FILE")
        )

        self.trials_path = self.get_data_path(self.get_config("TRIAL_NODES_FILE"))
        self.trials_sample_path = self.get_sample_path(
            self.get_config("TRIAL_SAMPLE_FILE")
        )

        self.num_sample_entries = int(self.get_config("NUM_SAMPLE_ENTRIES"))

        self.api_url: str = self.get_config("API_URL")
        self.api_fields = ",".join(
            [field.strip() for field in self.get_config("API_FIELDS").split(",")]
        )
        self.api_parameters: dict = {}

        root = logging.getLogger()
        root.setLevel(self.get_config("LOGGING_LEVEL"))

        # Check if the API fields are the same ones as the ones in the default
        # config, if not, log a warning
        default_config_dict = parse_config(
            registry_name=self.registry,
            config_path=DEFAULT_CONFIG_PATH,
        )
        api_fields = {field for field in self.api_fields.split(",")}
        default_fields = {
            field.strip() for field in default_config_dict["API_FIELDS"].split(",")
        }
        if api_fields != default_fields:
            logger.warning(
                f"The API fields in the config for {self.registry} are different "
                f"from the default config located at {DEFAULT_CONFIG_PATH}, this "
                f"may lead to unexpected results. Using the following fields:\n"
                f"{self.api_fields}"
            )
            if extra_in_default := default_fields - api_fields:
                logger.warning(
                    f"The following API fields are in the default config but "
                    f"not in the locally stored config: {', '.join(extra_in_default)}"
                )
            if extra_in_config := api_fields - default_fields:
                logger.warning(
                    f"The following API fields are in the locally stored config but "
                    f"not in the default config: {', '.join(extra_in_config)}"
                )


    def _create_data_dir(self) -> Path:
        """Create the data directory if it doesn't exist

        Returns
        -------
        Path
            The path to the data directory
        """

        data_dir = HOME_DIR / ".data" / "trialsynth" / self.registry
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def _create_config_dict(self) -> Optional[Dict[str, Any]]:
        """Load the configuration file into the config_file dictionary

        Returns
        -------
        Optional[Dict[str, Any]]
            A dictionary containing the configuration values. If the configuration
            file cannot be loaded, None is returned.
        """
        config_dir = HOME_DIR / ".config" / "trialsynth" / self.registry
        config_path = config_dir / "config.ini"
        if not config_path.is_file():
            config_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(DEFAULT_CONFIG_PATH, config_path)
            except Exception:
                logger.warning("Could not copy default config file.")

        try:
            config_dict = parse_config(self.registry, config_path)

        except Exception:
            logger.warning(
                "Could not load configuration file due to exception. "
                "Only environment variable equivalents will be used."
            )
            return None

        for key in config_dict.keys():
            if config_dict == "":
                config_dict[key] = None
            elif isinstance(config_dict[key], str):
                config_dict[key] = os.path.expanduser(config_dict[key])

        config_dict["DATA_DIR"] = self._create_data_dir()
        config_dict["SOURCE_KEY"] = self.registry
        return config_dict

    def get_config(
        self, key: str, failure_ok: bool = True
    ) -> Union[Path, str, int, None]:
        """Get a configuration value from the environment or config file.

        Parameters
        ----------
        key : str
            The key for the configuration value
        failure_ok : bool
            If False and the configuration is missing, an WhoConfigError is
                raised. If True, None is returned and no error is raised in case
                of a missing configuration. Default: False

        Returns
        -------
        Union[Path, str, int]
            The configuration value or None if the configuration value doesn't
            exist and failure_ok is set to True.

        Raises
        ------
        TrialSynthConfigError
            If the configuration value is missing and failure_ok is set to False.
        """

        err_msg = "Key %s not in environment or config file." % key
        if key in os.environ:
            return os.environ[key]
        elif key in self.config_dict:
            val = self.config_dict[key]
            # We interpret an empty value in the config file as a failure
            if val is None and not failure_ok:
                msg = "Key %s is set to an empty value in config file." % key
                raise TrialSynthConfigError(msg)
            else:
                return val
        elif not failure_ok:
            raise TrialSynthConfigError(err_msg)
        else:
            return None

    def get_data_path(self, filename: str) -> Path:
        """Get the full path to a file in the data directory
        Parameters
        ----------
        filename: str
            The name of the file to get the path for

        Returns
        -------
        Path
            The full path to the file in the data directory
        """
        return Path(self.data_dir, filename)

    def get_sample_path(self, filename: str) -> Path:
        """Get the full path to a file in the sample directory

        Parameters
        ----------
        filename: str
            The name of the file to get the path for

        Returns
        -------
        Path
            The full path to the file in the sample directory
        """
        return Path(self.sample_dir, filename)
