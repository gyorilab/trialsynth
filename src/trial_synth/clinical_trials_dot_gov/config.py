"""Clinicaltrials.gov processor configuration"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from ..config_environ import create_config_dict, get_config

CONFIG_DICT = create_config_dict("clinicaltrials")

HERE = Path(__file__).parent.resolve()
DATA_DIR = HERE.joinpath("data")
SAMPLE_DIR = DATA_DIR.joinpath("samples")

FIELDS = [
    "NCTId",
    "BriefTitle",
    "Condition",
    "ConditionMeshTerm",
    "ConditionMeshId",
    "InterventionName",
    "InterventionType",
    "InterventionMeshTerm",
    "InterventionMeshId",
    "StudyType",
    "DesignAllocation",
    "OverallStatus",
    "Phase",
    "WhyStopped",
    "SecondaryIdType",
    "SecondaryId",
    "StartDate",  # Month [day], year: "November 1, 2023", "May 1984" or NaN
    "StartDateType",  # "Actual" or "Anticipated" (or NaN)
    "ReferencePMID"  # these are tagged as relevant by the author, but not necessarily about the trial
]

root = logging.getLogger()
root.setLevel(get_config('LOGGING_LEVEL', CONFIG_DICT))


@dataclass
class Config:
    """
    User-mutable properties of Clinicaltrials.gov data processing
    """

    name = get_config('PROCESSOR_NAME', CONFIG_DICT)
    api_url = get_config('API_URL', CONFIG_DICT)
    api_parameters = {
        "fields": ",".join(FIELDS),  # actually column names, not fields
        "pageSize": 1000,
        "countTotal": "true"
    }

    unprocessed_file_path = Path(DATA_DIR, get_config('RAW_DATA', CONFIG_DICT))
    nodes_path = Path(DATA_DIR, get_config('NODES_FILE', CONFIG_DICT))
    nodes_indra_path = Path(DATA_DIR, get_config('NODES_INDRA_FILE', CONFIG_DICT))
    edges_path = Path(DATA_DIR, get_config('EDGES_FILE', CONFIG_DICT))
    node_types = ["BioEntity", "ClinicalTrial"]
