"""Gets Clinicaltrials.gov data from REST API or saved file"""

import logging
from pathlib import Path

import pandas as pd
import requests
from tqdm import trange
from typing import Optional

from .config import FIELDS
from .rest_api_response_models import UnflattenedTrial


TRIAL = {field: None for field in FIELDS}

logger = logging.getLogger(__name__)


class Fetcher:
    """Fetches Clinicaltrials.gov data from the REST API or a saved file

    Attributes
    ----------
    raw_data : DataFrame
        Raw data from the API or saved file
    url : str
        URL of the API endpoint
    request_parameters : dict
        Parameters to send with the API request
    total_pages : int
        Total number of pages of data that were fetched from the API

    Parameters
    ----------
    url : str
        URL of the API endpoint
    request_parameters : dict
        Parameters to send with the API request
    """

    def __init__(self, url, request_parameters):
        self.raw_data = pd.DataFrame()
        self.url = url
        self.request_parameters = request_parameters
        self.total_pages = 0

    def get_api_data(self, url: str, request_parameters: dict) -> None:
        """Fetches data from the Clinicaltrials.gov API

        Parameters
        ----------
        url : str
            URL of the API endpoint
        request_parameters : dict
            Parameters to send with the API request
        """
        logger.debug(f"Fetching Clinicaltrials.gov data from {url} with parameters {request_parameters}")

        try:
            self.read_next_page()
            # start on page "1" because we already did page 0 above. Note that we're zero-indexed,
            # so "1" is actually is the second page
            pages = 1 + self.total_pages
            for page in trange(1, pages, unit="page", desc="Downloading ClinicalTrials.gov"):
                self.read_next_page()

        except Exception:
            logger.exception(f"Could not fetch data from {url}")
            raise

    def read_next_page(self) -> None:
        json_data = send_request(self.url, self.request_parameters)
        studies = json_data.get("studies", [])
        flattened_data = flatten_data(studies)
        self.raw_data = pd.concat([self.raw_data, flattened_data])
        next_page_token = json_data.get("nextPageToken")
        self.request_parameters["pageToken"] = next_page_token
        if not self.total_pages:
            self.total_pages = json_data.get("totalCount") // self.request_parameters.get("pageSize")


def flatten_data(data: dict) -> pd.DataFrame:
    """Reformat API response data from hierarchical to tabular

    Parameters
    ----------
    data : dict
        Data from the API response

    Returns
    -------
    DataFrame
        Data fetched from the API in tabular format

    """
    logger.debug("Reformatting API response data from hierarchical to tabular")

    trials = []

    for trial_data in data:
        unflattened_trial = UnflattenedTrial(**trial_data)

        condition_browse_module = unflattened_trial.derived_section.condition_browse_module
        condition_meshes = condition_browse_module.condition_meshes

        condition_mesh_terms = [mesh.term for mesh in condition_meshes]
        condition_mesh_ids = [mesh.mesh_id for mesh in condition_meshes]

        arms_interventions_module = unflattened_trial.protocol_section.arms_interventions_module
        arms_interventions = arms_interventions_module.arms_interventions

        intervention_names = [
            i.name for i in arms_interventions
        ]
        intervention_types = [
            i.intervention_type.capitalize() for i in arms_interventions
        ]

        intervention_browse_module = unflattened_trial.derived_section.intervention_browse_module
        intervention_meshes = intervention_browse_module.intervention_meshes
        intervention_mesh_terms = [mesh.term for mesh in intervention_meshes]
        intervention_mesh_ids = [mesh.mesh_id for mesh in intervention_meshes]

        secondary_info = unflattened_trial.protocol_section.id_module.secondary_ids

        secondary_id_types = [s.id_type for s in secondary_info]
        secondary_ids = [s.secondary_id for s in secondary_info]

        reference_pmids = [r.pmid for r in unflattened_trial.protocol_section.id_module.secondary_ids]  # these are tagged as relevant by the author, but not necessarily about the trial

        conditions_str = join_if_not_empty(unflattened_trial.protocol_section.conditions_module.conditions)
        condition_mesh_terms_str = join_if_not_empty(condition_mesh_terms)
        condition_mesh_ids_str = join_if_not_empty(condition_mesh_ids)
        intervention_names_str = join_if_not_empty(intervention_names)
        intervention_types_str = join_if_not_empty(intervention_types)
        intervention_mesh_terms_str = join_if_not_empty(intervention_mesh_terms)
        intervention_mesh_ids_str = join_if_not_empty(intervention_mesh_ids)
        phases_str = join_if_not_empty(unflattened_trial.protocol_section.design_module.phases)
        if phases_str:
            phases_str = phases_str.replace("PHASE", "Phase ").replace("NA", "Not Applicable")
        secondary_id_types_str = join_if_not_empty(secondary_id_types)
        secondary_ids_str = join_if_not_empty(secondary_ids)
        reference_pmids_str = join_if_not_empty(reference_pmids)

        design_module = unflattened_trial.protocol_section.design_module

        design_allocation_str = design_module.design_info.allocation
        if design_allocation_str:
            design_allocation_str = design_allocation_str.replace("NA", "N/A").replace("NON_RANDOMIZED", "Non-Randomized").replace("RANDOMIZED", "Randomized")

        trial = TRIAL.copy()

        id_module = unflattened_trial.protocol_section.id_module
        status_module = unflattened_trial.protocol_section.status_module
        start_date_struct = status_module.start_date_struct

        trial["NCTId"] = id_module.nct_id
        trial["BriefTitle"] = id_module.brief_title
        trial["Condition"] = conditions_str
        trial["ConditionMeshTerm"] = condition_mesh_terms_str
        trial["ConditionMeshId"] = condition_mesh_ids_str
        trial["InterventionName"] = intervention_names_str
        trial["InterventionType"] = intervention_types_str
        trial["InterventionMeshTerm"] = intervention_mesh_terms_str
        trial["InterventionMeshId"] = intervention_mesh_ids_str
        trial["StudyType"] = design_module.study_type
        if trial["StudyType"]:
            trial["StudyType"] = trial["StudyType"].capitalize()
        trial["DesignAllocation"] = design_allocation_str
        trial["OverallStatus"] = status_module.overall_status
        if trial["OverallStatus"]:
            trial["OverallStatus"] = trial["OverallStatus"].capitalize()
        trial["Phase"] = phases_str
        trial["WhyStopped"] = status_module.why_stopped
        if trial["WhyStopped"]:
            trial["WhyStopped"] = trial["WhyStopped"].capitalize()
        trial["SecondaryIdType"] = secondary_id_types_str
        trial["SecondaryId"] = secondary_ids_str
        trial["StartDate"] = start_date_struct.date  # Month [day], year: "November 1, 2023", "May 1984" or NaN
        trial["StartDateType"] = start_date_struct.date_type  # "Actual" or "Anticipated" (or NaN)
        trial["ReferencePMID"] = reference_pmids_str

        trials.append(trial)

    return pd.DataFrame.from_dict(trials)


def load_saved_data(path: Path) -> pd.DataFrame:
    """Load saved Clinicaltrials.gov data from a file

    Parameters
    ----------
    path : Path
        Path to the saved data file
    """
    logger.debug(f"Loading Clinicaltrials.gov data from {path}")

    try:
        return pd.read_csv(path, sep="\t")
    except Exception:
        logger.exception(f"Could not load data from {path}")


def send_request(url: str, params: dict) -> dict:
    """Send a request to the Clinicaltrials.gov API and return the response as JSON

    Parameters
    ----------
    url : str
        URL of the API endpoint
    params : dict
        Parameters to send with the API request

    Returns
    -------
    dict
        JSON response from the API
    """
    try:
        response = requests.get(url, params)
        return response.json()
    except Exception:
        logger.exception(f"Error with request to {url} using params {params}")
        raise


def join_if_not_empty(data: list, delimiter: str = "|") -> Optional[str]:
    """Join a list of strings with a delimiter if the list is not empty

    Parameters
    ----------
    data : list
        List of strings to join
    delimiter : Optional[str]
        Delimiter to use when joining the strings. Default: "|"

    """
    if all(data):
        return delimiter.join(data)
    return None
