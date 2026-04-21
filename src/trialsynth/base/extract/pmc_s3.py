"""PMC Cloud S3 text fetching helpers."""

import re
import xml.etree.ElementTree as ET
from functools import lru_cache

import requests

PMC_S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
_S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


@lru_cache(maxsize=10000)
def get_s3_versions(pmcid: str) -> tuple[int, ...]:
    """Return sorted tuple of available version numbers for a PMC article on S3."""
    res = requests.get(PMC_S3_BASE, params={"prefix": f"{pmcid}.", "delimiter": "/"})
    res.raise_for_status()
    tree = ET.fromstring(res.content)
    versions = []
    for el in tree.findall("s3:CommonPrefixes/s3:Prefix", _S3_NS):
        m = re.match(rf"{re.escape(pmcid)}\.(\d+)/", el.text or "")
        if m:
            versions.append(int(m.group(1)))
    return tuple(sorted(versions))


def get_latest_s3_version(pmcid: str) -> int | None:
    """Return the latest available version number, or None if not on S3."""
    versions = get_s3_versions(pmcid)
    return max(versions) if versions else None


def _get_s3_artifact(
    pmcid: str, ext: str, version: int | None = None
) -> requests.Response | None:
    """Fetch a file artifact for a PMC article from the public S3 bucket."""
    if version is None:
        version = get_latest_s3_version(pmcid)
        if version is None:
            return None
    url = f"{PMC_S3_BASE}/{pmcid}.{version}/{pmcid}.{version}.{ext}"
    res = requests.get(url, timeout=60)
    res.raise_for_status()
    return res


def get_text_s3(pmcid: str, version: int | None = None) -> str | None:
    """Return plain text for a PMC article from S3, or None if unavailable."""
    try:
        res = _get_s3_artifact(pmcid, "txt", version=version)
        return res.text if res is not None else None
    except Exception:
        return None
