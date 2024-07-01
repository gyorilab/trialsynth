import logging
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


def store_dataframe_as_flat_file(dataframe: pd.DataFrame, path: Path, delimiter: str = "\t", index: bool = False) -> None:
    """Stores a DataFrame as a flat file.

    Parameters
    ----------
    dataframe : DataFrame
        DataFrame to store
    path : Path
        Path to store the DataFrame
    delimiter : str
        Delimiter for the flat file
    index : bool, default False
        Whether to include the index in the flat file
    """
    try:
        dataframe.to_csv(path, sep=delimiter, index=index)
    except Exception:
        logger.exception(f"Error saving dataframe to {path}")
