import re
import logging

from lxml import etree
import pandas as pd
from tqdm import tqdm
from typing import Optional
from pathlib import Path
from .config import DATA_DIR
import bioregistry

logger = logging.getLogger(__name__)

PREFIXES = {
    "ISRCTN": "isrctn",
    "ACTRN": "anzctr",
    "ANZCTR": "anzctr",  # xxx
    "NCT": "clinicaltrials",
    "ClinicalTrials.gov": "clinicaltrials",  # xx
    "DRKS": "drks",
    "German Clinical Trials Register": "drks",  # xxx
    "RBR": "rebec",
    "REBEC": "rebec",  ###
    "CRIS": "kcris",  ###
    "PACTR": "pactr",
    "TCTR": "tctr",
    "RPCEC": "rpcec",
    "EUCTR": "euclinicaltrials",
    "EU Clinical Trials Register": "euclinicaltrials",  ###
    "JPRN-jRCT": "jrct",
    "JPRN-UMIN": "uminctr",  # University hospital Medical Information Network
    "JPRN-C": "uminctr",  # new ID format starting with C
    "Clinical Trials Information System": "ctis",
    "CTIS": "ctis",  # site broken
    "LBCTR": "lctr",  # Lebanon Clinical Trials Registry
    "ITMCTR": "itmctr",  # International Traditional Medicine Clinical Trial Registry
    "IRCT": "irct",  # Iranian clinical trials - IDs don't match web page
    "KCT": "kcris",
    "CTRI": "ctri",  # Indian clinical trials - IDs don't match web page
    "ChiCTR": "chictr",  # Chinese Clinical Trial Registry - same
    "SLCTR": "slctr",  # need to change slashes to dashes to resolve
    "IFV": "rpcec",  # Cuba: Registro Público Cubano de Ensayos Clínicos
    "jRCT": "jrct",  # Japan Registry of Clinical Trials
    "PHRR": "phrr",  # Philippines trial registry
    "NL": "ictrp",  # Netherlands old registry, find at trialsearch.who.int using NLXXXX
    "PER": "repec",  # Clinical Trials Peruvian Registry
}


def get_patterns() -> dict:
    """
    Get compiled regular expression patterns for the prefixes
    """
    rv = {}
    for k, v in PREFIXES.items():
        if not v:
            continue
        pattern = bioregistry.get_pattern(v)
        if not pattern:
            tqdm.write(f"missing pattern for {v} in bioregistry")
            continue
        rv[k] = re.compile(pattern)
    return rv


PATTERNS = get_patterns()


def findtext(trial: etree.Element, k: str) -> str:
    """Find the text of a child element of a trial

    Parameters
    ----------
    trial : etree.Element
        The trial element

    k : str
        The key of the child element

    Returns
    -------
    str
        The text of the child element
    """
    v = trial.find(k)
    if (v is not None) and (v.text is not None):
        return trial.find(k).text.replace("<br>", "\n").strip()
    return ""


def makelist(s: Optional[str], delimeter: str = '.') -> list:
    """Find a list of values from an element joined by semicolons

    Parameters
    ----------
    s : Optional[str]
        The string to split
    delimeter : str
        The delimeter to split by

    Returns
    -------
    list
        The list of values
    """

    if s and not pd.isna(s):
        s = s.removeprefix('"').removesuffix('"')
        return sorted(x for x in {x.strip() for x in s.split(delimeter)} if x)
    return []


def make_str(s: str):
    """Return a stripped string if it is not empty

    Parameters
    ----------
    s : str
        The string to check

    Returns
    -------
    str
        The string if it is not empty
    """
    if s and not pd.isna(s):
        return s.strip()

    return ''


def matches_pattern(s: str) -> Optional[str]:
    """Matches a string to a pattern and returns the prefix if it matches.

    Parameters
    ----------
    s : str
        The string to match

    Returns
    -------
    Optional[str]
        The prefix

    """
    for prefix, pattern in PATTERNS.items():
        if pattern.match(s):
            return PREFIXES[prefix]


def transform_mappings(s: str) -> Optional[list[str]]:
    """Transforms a string of mappings into a list of CURIEs

    Parameters
    ----------
    s : str
        The string of mappings

    Returns
    -------
    Optional[list[str]]
        The list of CURIEs
    """
    if pd.isna(s) or not s:
        return None
    curies = []
    for x in s.split(";"):
        x = x.strip()
        if x.lower() in {"nil", "nil known", "none"}:
            continue
        prefix = matches_pattern(x)
        if not prefix:
            continue
        curies.append(bioregistry.curie_to_str(prefix, x))
    if not curies:
        return None
    return curies


def ensure_output_directory_exists(path: Path) -> None:
    """Ensures that the output directory exists

    Parameters
    ----------
    path : Path
        Path to the output directory
    """
    try:
        logger.info(f"Ensuring directory exists: {path}")
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception(f"An error occurred trying to create {path}")
        raise
