import gzip
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from tqdm import tqdm

from .util import PATTERNS

logger = logging.getLogger(__name__)


EXPECTED_TYPES = (
    "string",
    "CURIE",
    "LABEL",
    "DESIGN",
    "OUTCOME",
)


class DataTypeError(TypeError):
    """Raised when a data value is not of the expected type"""


class UnknownTypeError(TypeError):
    """Raised when a data type is not recognized."""


class WrongFormatError(TypeError):
    """Raised when a data type is not formatted correctly."""


class Validator:
    def __init__(self, catch_exceptions: bool = True):
        self.path: Optional[Path] = None
        self.data: pd.DataFrame = pd.DataFrame()
        self.catch_exceptions: bool = catch_exceptions

    def __call__(self, path: Path):
        self.validate(path)

    def validate(self, path: Path):
        self.path = path

        self.create_rows()
        self.validate_headers()

        for col, data in self.data.iteritems():
            name, data_type = col.split(":")
            tqdm.pandas(
                desc=f"Validating '{name}' column of type '{data_type}'",
                unit=name,
                unit_scale=True,
            )
            data.progress_apply(
                lambda x, data_type=data_type: self.validate_data(data_type, x)
            )

    def create_rows(self):
        logger.info(f"Loading data to validate from compressed tsv file: {self.path}")

        n_lines = sum(1 for line in gzip.open(self.path, mode="rt"))
        with tqdm(
            total=n_lines, desc="Loading data", unit="lines", unit_scale=True
        ) as pbar:
            chunks = []
            for chunk in pd.read_csv(self.path, sep="\t", chunksize=1000):
                chunks.append(chunk)
                pbar.update(len(chunk))
        self.data = pd.concat(chunks, ignore_index=True)

    def validate_headers(self) -> None:
        """Check for data types in the headers

        Parameters
        ----------
        headers : Iterable[str]
            The headers to check for data types

        Raises
        ------
        TypeError
            If a data type is not recognized by Neo4j
        """
        headers = self.data.columns
        for header in headers:
            # headers are formatted header:TYPE
            if ":" in header and header.split(":")[1]:
                dtype = header.split(":")[1]

                # strip trailing [] for array types
                if dtype.endswith("[]"):
                    dtype = dtype.removesuffix("[]")

                if dtype not in EXPECTED_TYPES:
                    raise UnknownTypeError(
                        f"Invalid header type '{dtype}' for header {header}"
                    )

    def validate_data(self, data_type: str, value: Any):
        """Validate that the data type matches the value.

        Parameters
        ----------
        data_type : str
            The Neo4j data type to validate against.
        value : Any
            The value to validate.

        Raises
        ------
        DataTypeError
            If the value does not validate against the Neo4j data type.
        UnknownTypeError
            If data_type is not recognized as a Neo4j data type.
        """

        null_data = [None, ""]
        if value in null_data:
            return ""

        if isinstance(value, str):
            value_list = value.split(";") if data_type.endswith("[]") else [value]
        else:
            value_list = [value]
        value_list = [val for val in value_list if val not in null_data]
        if not value_list:
            return

        if data_type == "string":
            for val in value_list:
                if isinstance(val, (int, float)):
                    try:
                        val = str(val)
                    except ValueError:
                        msg = (
                            f"Data value '{val}' is of the wrong type to conform with Neo4j type {data_type}. "
                            f"Expected a value of type str or int, but got value of type {type(val)} instead."
                        )
                        if not self.catch_exceptions:
                            raise DataTypeError(msg) from None
                        logger.warning(msg)
            return

        if data_type == "CURIE":
            for val in value_list:
                ns, *id_split = val.split(":")
                id = ":".join(id_split)

                if ns in PATTERNS.keys():
                    if PATTERNS[ns].match(id):
                        continue
                    if not self.catch_exceptions:
                        raise WrongFormatError(
                            f"ID for namespace '{ns} does not follow regex pattern"
                        )
                if not self.catch_exceptions:
                    raise TypeError(
                        f"Namespace value '{ns}' is not in recognized namespaces"
                    )
            return

        if data_type == "DESIGN":
            for val in value_list:
                design_attrs = [val.strip() for val in val.split(";")]
                attr_labels = ["Purpose:", "Allocation:", "Masking:", "Assignment:"]

                invalid_format = True

                if len(design_attrs) == 1:
                    return

                for design_attr, attr_label in zip(design_attrs, attr_labels):
                    invalid_format = not design_attr.startswith(attr_label)

                msg = f"Design data '{val}' not in expected format."
                if invalid_format:
                    if not self.catch_exceptions:
                        raise WrongFormatError(msg)
                    logger.warning(msg)
            return

        if data_type == "OUTCOME":
            for val in value_list:
                outcome_attrs = [val.strip() for val in val.split(",")]
                attr_labels = ["Measure:", "Time Frame:"]

                invalid_format = len(outcome_attrs) != 2

                for outcome_attr, attr_label in zip(outcome_attrs, attr_labels):
                    invalid_format = not outcome_attr.startswith(attr_label)

                msg = f"Outcome data '{val}' not in expected format."
                if invalid_format:
                    if not self.catch_exceptions:
                        raise WrongFormatError(msg)
                    logger.warning(msg)
            return
