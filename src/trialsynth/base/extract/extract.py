import argparse
import json
import re
import tqdm
import os
import glob
from openai import OpenAI
from pypdf import PdfReader


def extract_trial_ids(text):
    """Extract clinical trial identifiers from text."""
    ids = []
    # NCT numbers (ClinicalTrials.gov)
    nct_matches = re.findall(r'NCT\d{7,8}', text)
    ids.extend(sorted(set(nct_matches)))
    # EudraCT numbers
    eudract_matches = re.findall(r'\d{4}-\d{6}-\d{2}', text)
    ids.extend(sorted(set(eudract_matches)))
    return ids

LLM_MODEL = 'gpt-4o'


TRIAL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "study_info": {
            "type": "string",
            "description": "Basic information about the study in a standardized format. "
                           "Example: 'Title: Trastuzumab Emtansine for HER2-Positive Advanced Breast Cancer | "
                           "Trial: EMILIA | Year: 2012 | Journal: New England Journal of Medicine'"
        },
        "arms": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the arms of the "
                           "clinical study, i.e., groups of patients getting "
                           "the same treatment"
        },
        "enrollment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the number of patients "
                           "enrolled in the study, including total enrollment and "
                           "the size of each arm or cohort"
        },
        "response": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the response to "
                           "treatment vs control in different arms of the study."
        },
        "endpoints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the endpoints of "
                           "the study, including primary and secondary endpoints."
        },
        "adverse_events": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans mentioning the adverse events "
                           "associated with treatment.",
        },
        "inclusion_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the inclusion criteria "
                           "for patient enrollment in the study."
        },
        "exclusion_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of raw text spans describing the exclusion criteria "
                           "that disqualify patients from the study."
        },
    },
    "required": ["study_info", "arms", "enrollment", "response", "endpoints", "adverse_events", "inclusion_criteria", "exclusion_criteria"],
    "additionalProperties": False
}


def call_llm(client, messages, schema):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "clinical_trial_results",
                "strict": True,
                "schema": schema
            }
        }
    )

    if not response.choices or not response.choices[0].message.content:
        print("Empty response from API")
        return {}

    return json.loads(response.choices[0].message.content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract clinical trial data from PDFs')
    parser.add_argument('--force', action='store_true', help='Force re-extraction even if JSON output exists')
    args = parser.parse_args()

    parts = []
    for key, entry in TRIAL_RESULT_SCHEMA['properties'].items():
        part = f'- {key}: {entry["description"]}'
        parts.append(part)
    fields_str = '\n'.join(parts)

    client = OpenAI()

    pdf_fnames = glob.glob("*.pdf")
    pbar = tqdm.tqdm(pdf_fnames)
    for pdf_fname in pbar:
        pbar.set_description(pdf_fname)
        out_fname = os.path.splitext(pdf_fname.replace(' ', '_'))[0] + '.json'

        if os.path.exists(out_fname) and not args.force:
            continue

        txt_fname = os.path.splitext(pdf_fname)[0] + '.txt'
        if os.path.exists(txt_fname):
            with open(txt_fname, 'r') as fh:
                text = fh.read()
        else:
            reader = PdfReader(pdf_fname)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            with open(txt_fname, 'w') as fh:
                fh.write(text)

        messages = [
            {
                "role": "system",
                "content": (
                    "Extract the following structured fields related to clinical trial results from the given biomedical text.\n"
                    f"{fields_str}\n\n"
                    "Only include exact text spans from the document."
                )
            },
            {"role": "user", "content": f"Text: {text}"}
        ]

        result = call_llm(client, messages, TRIAL_RESULT_SCHEMA)
        result['trial_ids'] = extract_trial_ids(text)
        with open(out_fname, 'w') as fh:
            json.dump(result, fh, indent=1)

