import logging

import csv
import pandas as pd
from tqdm import tqdm
from pathlib import Path

import bioregistry

from .config import FIELDS, Config
from .trial_model import WHOTrial
from .util import PREFIXES, makelist, transform_mappings, make_str
from .validate import is_valid
from .fetch import load_saved_pickled_data

logger = logging.getLogger(__name__)

def ensure_df(config: Config = Config()) -> pd.DataFrame:
    """
    Ensure that the DataFrame is loaded from a saved pickle file or from the CSV file

    Parameters
    ----------
    config: Config
        Configuration for WHO data processing. Default: Config()

    Returns
    -------
    pd.DataFrame
        The DataFrame of the WHO data
    """
    if config.parsed_pickle_path.is_file():
        return load_saved_pickled_data(config.parsed_pickle_path)

    df = transform_csv_data(config.csv_path)
    df.to_pickle(config.parsed_pickle_path)
    return df

def transform_csv_data(path: Path) -> pd.DataFrame:
    """Transforms WHO data from CSV into a DataFrame

    Parameters
    ----------
    path : Path
        CSV data file path
    
    Returns
    -------
    pd.DataFrame
        Transformed WHO data
    """
    rows = []
    with open(path, mode='r') as file:
        lines = [line for line in file]

        for trial in tqdm(csv.reader(lines), desc="Reading CSV WHO data", total=len(lines), unit='lines'):
            trial_id = trial[0].strip()
            trial_id = trial_id.replace('\ufeff', '')
            for p, prefix in PREFIXES.items():
                if trial_id.startswith(p) or trial_id.startswith(p.lower()):
                    break
            else:
                msg = f"could not identify {trial_id}"
                raise ValueError(msg)

            if trial_id.startswith("EUCTR"):
                trial_id = trial_id.removeprefix("EUCTR")
                trial_id = "-".join(trial_id.split("-")[:3])

            # handling inconsistencies with ChiCTR trial IDs
            if trial_id.lower().startswith("chictr-"):
                trial_id = "ChiCTR-" + trial_id.lower().removeprefix("chictr-").upper()

            trial_id = trial_id.removeprefix("JPRN-").removeprefix("CTIS").removeprefix("PER-")

            if not is_valid(p, trial_id):
                tqdm.write(f"Failed validation: {trial_id}")

            who_trial = WHOTrial(
                curie = bioregistry.curie_to_str(prefix, trial_id),
                name = make_str(trial[3]),
                study_type = make_str(trial[18]),
                study_design= makelist(trial[19], '.'),
                countries = makelist(trial[28], '.'),
                conditions = makelist(trial[29], ';'),
                intervention = makelist(trial[30], ';'),
                primary_outcome = make_str(trial[36]),
                secondary_outcome = make_str(trial[37]),
                mappings = make_str(trial[2])
            )

            rows.append(
                (
                    who_trial.curie,
                    who_trial.name,
                    who_trial.study_type,
                    who_trial.study_design,
                    who_trial.countries,
                    who_trial.conditions,
                    who_trial.intervention,
                    who_trial.primary_outcome,
                    who_trial.secondary_outcome,
                    who_trial.mappings,
                )
            )

        df = pd.DataFrame(
            rows,
            columns=FIELDS
        ).sort_values("curie")

        df["mappings"] = df.mappings.map(transform_mappings)
        return df
