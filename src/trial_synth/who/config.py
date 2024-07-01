from dataclasses import dataclass
from pathlib import Path
from ..config_environ import create_config_dict, get_config

CONFIG_DICT = create_config_dict("who")

HERE = Path(__file__).parent.resolve()
DATA_DIR = HERE.joinpath("data")
SAMPLE_DIR = DATA_DIR.joinpath("samples")
NER_DIR = DATA_DIR.joinpath("ner")

SOURCE_KEY = "who"

FIELDS = [
    "curie",
    "name",
    "type",
    "design",
    "countries",
    "conditions",
    "interventions",
    "primary_outcome",
    "secondary_outcome",
    "mappings"
]


@dataclass
class Config:
    """
    User-mutable properties of WHO data processing
    """

    current_path = HERE
    data_dir_path = DATA_DIR
    sample_dir_path = SAMPLE_DIR
    ner_dir_path = NER_DIR

    csv_path = DATA_DIR.joinpath(get_config('RAW_DATA', CONFIG_DICT))
    parsed_pickle_path = DATA_DIR.joinpath(get_config('PROCESSED_FILE', CONFIG_DICT))
    sample_path = SAMPLE_DIR.joinpath(get_config('PROCESSED_SAMPLE', CONFIG_DICT))
    nodes_path = DATA_DIR.joinpath(get_config('NODES_FILE', CONFIG_DICT))
    edges_path = DATA_DIR.joinpath(get_config('EDGES_FILE', CONFIG_DICT))
    mappings_path = DATA_DIR.joinpath(get_config('MAPPINGS_FILE', CONFIG_DICT))

    source_key = SOURCE_KEY
