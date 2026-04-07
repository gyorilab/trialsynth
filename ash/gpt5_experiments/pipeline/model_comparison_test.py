"""
Model comparison test: run 10 HGNC-positive PMIDs through multiple models
and save outputs to separate folders for side-by-side comparison.

Usage:
    python model_comparison_test.py

Outputs to:
    dataset_intersection/model_comparison/{model_name}/{pmid}.json
"""

import json
import logging
import sys
from pathlib import Path

from openai import OpenAI

# Import extraction logic from main extractor
sys.path.insert(0, str(Path(__file__).parent))
import extractor_anchor as ea

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

PMIDS = [
    "16236737", "16236738", "17151364", "17822557", "18083065",
    "18156492", "18226581", "18316791", "18482659", "18612102",
]

MODELS = [
    "gpt-5.4-mini",
    "gpt-5.4-mini-hgnc-prompt",       # patched system prompt
]

# Patched system prompt that explicitly instructs use of official HGNC symbols
PATCHED_SYSTEM_PROMPT = (
    "You are a clinical data scientist. Transform medical text into a queryable database structure. "
    "1. For EVERY single extracted data point (including Arm definitions, Dosages, Inclusion/Exclusion Criteria, "
    "Genetic Markers, Metrics, and Adverse Events), you MUST return a short verbatim anchor phrase "
    "(5 to 15 words maximum) copied directly from the source text that uniquely identifies the sentence "
    "containing the evidence. Use the field 'evidence_anchor' for this. "
    "Do NOT copy the full sentence — just a unique short phrase from it. "
    "This anchor is used programmatically to locate the full sentence, so it must be verbatim. "
    "2. Extract qualitative results and metrics. "
    "3. Assign safety events to arms. "
    "4. Embed structured metrics into Arms and Comparisons. When multiple subgroups "
    "exist for one outcome, isolate the subgroup name (e.g., 'Women <50') into the 'name' field "
    "and the clean numeric/CI result into 'value_text'. Do NOT repeat the baseline comparison. "
    "5. Isolate genetic biomarkers into the 'genetic' block using official HGNC Gene Symbols and HGVS nomenclature. "
    "Always use the official HGNC gene symbol in the text field (e.g. ERBB2 not HER2, MYC not cMYC, "
    "ABL1 not ABL, MS4A1 not CD20) so downstream grounding tools can resolve them correctly."
)

TXT_DIR = Path("D:/CS/GyoriLabs/trialsynth/ash/production_pipeline/content/txt")
OUT_ROOT = Path("D:/CS/GyoriLabs/trialsynth/ash/gpt5_experiments/dataset_intersection/model_comparison")
GPT52_DIR = Path("D:/CS/GyoriLabs/trialsynth/ash/gpt5_experiments/dataset_intersection/grounded_anchor_genetic")


def run_model(model: str, client: OpenAI):
    out_dir = OUT_ROOT / model.replace(".", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    use_low_temp = model.endswith("-t02")
    base = model.replace("-t02", "")
    use_patched_prompt = base.endswith("-hgnc-prompt")
    api_model = base.replace("-hgnc-prompt", "") if use_patched_prompt else base
    temperature = 0.2 if use_low_temp else 1.0

    for pmid in PMIDS:
        out_file = out_dir / f"{pmid}.json"
        if out_file.exists():
            logger.info(f"  [{model}] {pmid} already exists, skipping")
            continue

        txt_path = TXT_DIR / f"{pmid}.txt"
        if not txt_path.exists():
            logger.warning(f"  [{model}] {pmid} - text not found")
            continue

        text = txt_path.read_text(encoding="utf-8")
        try:
            ea.LLM_MODEL = api_model
            if use_patched_prompt:
                import extractor_anchor as _ea
                orig_fn = _ea.extract_trial_data

                def patched_extract(client, text, pmid):
                    import json as _json
                    sentences = _ea.split_sentences(text)
                    response = client.chat.completions.create(
                        model=api_model,
                        temperature=temperature,
                        messages=[
                            {"role": "system", "content": PATCHED_SYSTEM_PROMPT},
                            {"role": "user", "content": f"Text (PMID {pmid}): {text}"}
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "clinical_trial_extraction_anchor",
                                "strict": True,
                                "schema": _ea.TRIAL_RESULT_SCHEMA_ANCHOR
                            }
                        }
                    )
                    raw = _json.loads(response.choices[0].message.content)
                    resolved = _ea.resolve_anchors(raw, sentences)
                    return resolved, response.usage

                result, usage = patched_extract(client, text, pmid)
            else:
                result, usage = ea.extract_trial_data(client, text, pmid)

            out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            logger.info(f"  [{model}] {pmid} | input: {usage.prompt_tokens} | output: {usage.completion_tokens}")
        except Exception as e:
            logger.error(f"  [{model}] {pmid} failed: {e}")


def compare_genetic(pmid: str, model: str) -> dict:
    """Compare genetic block between gpt-5.2 baseline and test model."""
    baseline_path = GPT52_DIR / f"{pmid}.json"
    test_path = OUT_ROOT / (model.replace(".", "_") + "_grounded") / f"{pmid}.json"

    if not baseline_path.exists() or not test_path.exists():
        return {"pmid": pmid, "model": model, "status": "missing"}

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    test = json.loads(test_path.read_text(encoding="utf-8"))

    def get_hgnc(data):
        hits = []
        for entry in data.get("genetic", {}).get("grounded_inclusion", []):
            for g in entry.get("groundings", []):
                if g.get("info", {}).get("db") == "HGNC":
                    hits.append(g["info"].get("entry_name", ""))
        return hits

    baseline_genes = get_hgnc(baseline)
    test_genes = get_hgnc(test)

    baseline_set = set(baseline_genes)
    test_set = set(test_genes)
    return {
        "pmid": pmid,
        "model": model,
        "baseline_genes": baseline_genes,
        "test_genes": test_genes,
        "match": baseline_set <= test_set,  # recall-based: baseline ⊆ test
        "extra": sorted(test_set - baseline_set),
        "missing": sorted(baseline_set - test_set),
    }


if __name__ == "__main__":
    client = OpenAI()

    for model in MODELS:
        logger.info(f"\n=== Running {model} ===")
        run_model(model, client)

    # Print comparison summary
    print("\n\n=== GENETIC COMPARISON SUMMARY ===")
    print(f"{'PMID':<12} {'Model':<40} {'Match':<8} {'Missing':<25} {'Extra'}")
    print("-" * 110)
    for model in MODELS:
        yes = 0
        for pmid in PMIDS:
            r = compare_genetic(pmid, model)
            if r.get("status") == "missing":
                print(f"{pmid:<12} {model:<40} MISSING")
                continue
            match = "YES" if r["match"] else "NO"
            if r["match"]: yes += 1
            missing_str = str(r["missing"]) if r["missing"] else "-"
            extra_str = str(r["extra"]) if r["extra"] else "-"
            print(f"{pmid:<12} {model:<40} {match:<8} {missing_str:<25} {extra_str}")
        print(f"  -> {model}: {yes}/{len(PMIDS)} recall-match\n")
