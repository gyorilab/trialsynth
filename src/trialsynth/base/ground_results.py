"""
Ground genetic markers and clinical criteria in extracted JSON files using local Gilda.

Reads raw anchor JSONs and writes grounded versions with HGNC groundings for
genetic markers and MESH/DOID/EFO groundings for inclusion/exclusion criteria.

Usage:
    python ground_results.py --input-dir <raw_dir> --output-dir <grounded_dir>
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import gilda
import pystow

logger = logging.getLogger(__name__)


def get_gilda_grounding(text: str, sources: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Ground text using local Gilda library (replaces REST API call)."""
    if not text:
        return None
    try:
        results = gilda.ground(text, namespaces=sources)
        if results:
            top = results[0].term
            return {
                "entry_name": top.entry_name,
                "db": top.db,
                "id": top.id,
                "score": results[0].score
            }
    except Exception:
        pass
    return None


ANNOTATE_STOPLIST = {
    'FISH', 'IV', 'WT', 'HR', 'CI', 'OR', 'RR', 'OS', 'PFS', 'CR', 'PR',
    'SD', 'PD', 'CT', 'MRI', 'PCR', 'IHC', 'AE', 'SAE', 'PS', 'ECOG',
    'HET', 'SET', 'CAT', 'ACT', 'ALL', 'CML', 'AML', 'NHL', 'DNA', 'RNA',
    'ATP', 'GTP', 'II', 'III', 'BL', 'large', 'real'
}


def _annotate_fallback(evidence_text: str) -> List[Dict[str, Any]]:
    """Fallback: run gilda.annotate() on full sentence, return HGNC hits with score > 0.75."""
    if not evidence_text:
        return []
    try:
        results = gilda.annotate(evidence_text)
        hits = []
        for r in results:
            if not r.matches:
                continue
            top = r.matches[0]
            if top.term.db != 'HGNC':
                continue
            if top.score < 0.75:
                continue
            if len(r.text) < 4:
                continue
            if r.text.upper() in ANNOTATE_STOPLIST or r.text in ANNOTATE_STOPLIST:
                continue
            hits.append({"symbol": r.text, "info": {
                "entry_name": top.term.entry_name,
                "db": top.term.db,
                "id": top.term.id,
                "score": top.score,
                "source": "annotate_fallback"
            }})
        return hits
    except Exception:
        return []


def ground_marker(item: Any) -> Dict[str, Any]:
    if isinstance(item, str):
        text = item
        evidence_text = "Retrospective migration"
    else:
        text = item.get("text", "")
        evidence_text = item.get("evidence_text", "Retrospective migration")

    raw = text.strip()
    parts = re.split(r'[:/-]', raw)
    symbols = [re.findall(r'[A-Z0-9]+', p, re.IGNORECASE) for p in parts]
    symbols = [s[0] for s in symbols if s]

    groundings = []
    for s in symbols:
        if len(s) < 2:
            continue
        g = get_gilda_grounding(s, sources=["HGNC", "UP", "MESH"])
        if g:
            groundings.append({"symbol": s, "info": g})

    if not groundings and evidence_text and evidence_text != "Retrospective migration":
        fallback_hits = _annotate_fallback(evidence_text)
        groundings.extend(fallback_hits)

    variant = None
    var_match = re.search(r"(p\.[A-Za-z0-9]+|[A-Z][0-9]{2,4}[A-Z])", raw, re.IGNORECASE)
    if var_match:
        variant = var_match.group(1)

    return {
        "text": text,
        "evidence_text": evidence_text,
        "groundings": groundings,
        "variant": variant
    }


def ground_json(input_path: Path, output_path: Path) -> None:
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if "results" in data:
        data["results"] = [
            {"text": r, "evidence_text": "Retrospective migration"} if isinstance(r, str) else r
            for r in data["results"]
        ]

    grounded_genetic = []
    for item in data.get('genetic', {}).get('genetic_inclusion', []):
        grounded_genetic.append(ground_marker(item))
    data['genetic']['grounded_inclusion'] = grounded_genetic

    grounded_inclusion = []
    for item in data.get('inclusion_criteria', [])[:5]:
        if isinstance(item, str):
            text = item
            ev = "Retrospective migration"
        else:
            text = item.get("text", "")
            ev = item.get("evidence_text", "Retrospective migration")
        match = get_gilda_grounding(text, sources=["MESH", "DOID", "EFO"])
        grounded_inclusion.append({"text": text, "evidence_text": ev, "grounding": match})
    data['grounded_inclusion_criteria'] = grounded_inclusion

    grounded_exclusion = []
    for item in data.get('exclusion_criteria', [])[:5]:
        if isinstance(item, str):
            text = item
            ev = "Retrospective migration"
        else:
            text = item.get("text", "")
            ev = item.get("evidence_text", "Retrospective migration")
        match = get_gilda_grounding(text, sources=["MESH", "DOID", "EFO"])
        grounded_exclusion.append({"text": text, "evidence_text": ev, "grounding": match})
    data['grounded_exclusion_criteria'] = grounded_exclusion

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=pystow.module("indra", "cogex", "clinical_trial_results", "raw").base)
    parser.add_argument("--output-dir", type=Path, default=pystow.module("indra", "cogex", "clinical_trial_results", "grounded").base)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_files = list(args.input_dir.glob("*.json"))
    logger.info(f"Grounding {len(json_files)} files...")
    for i, jf in enumerate(json_files):
        out = args.output_dir / jf.name
        if out.exists():
            continue
        ground_json(jf, out)
        if (i + 1) % 50 == 0:
            logger.info(f"  {i + 1}/{len(json_files)} done")
    logger.info("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
