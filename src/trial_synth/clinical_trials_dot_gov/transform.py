from collections import Counter
import logging
import re
from typing import Iterator, Optional

from addict import Dict
import pandas as pd
from tqdm import tqdm

import gilda
from indra.databases import mesh_client
from indra.ontology.standardize import standardize_name_db_refs
from indra.statements.agent import get_grounding


logger = logging.getLogger(__name__)


def or_na(x):
    """Return None if x is NaN, otherwise return x"""
    return None if pd.isna(x) else x


def isna(x):
    """
    Check if a value is NaN or None.
    """
    return True if pd.isna(x) or not x else False


def _get_phase(phase_string: str) -> int:
    """
    Extract the phase number from a phase string.

    Parameters
    ----------
    phase_string : str
        The phase string to extract the phase number from.

    Returns
    -------
    int
        The phase number extracted from the phase string.
    """
    if phase_string and pd.notna(phase_string) and phase_string[-1].isdigit():
        return int(phase_string[-1])
    return -1


def _get_start_year(start_date: str) -> Optional[int]:
    """
    Extract the start year from a start date string.

    Parameters
    ----------
    start_date : str
        The start date string to extract the start year from.

    Returns
    -------
    Optional[int]
        The start year extracted from the start date string.
    """
    if isna(start_date):
        return None
    match = re.search(r"\d{4}", start_date)
    if match:
        return int(match[0])
    return None


def get_correct_mesh_id(mesh_id: str, mesh_term: Optional[str]=None) -> str:
    """
    Get a correct MeSH ID from a possibly incorrect one.

    Parameters
    ----------
    mesh_id : str
        The MeSH ID to correct.
    mesh_term : Optional[str]
        The MeSH term corresponding to the MeSH ID. Default is None.

    Returns
    -------
    str
        The corrected MeSH ID.
    """
    # A proxy for checking whether something is a valid MeSH term is
    # to look up its name
    name = mesh_client.get_mesh_name(mesh_id, offline=True)
    if name:
        return mesh_id
    # A common issue is with zero padding, where 9 digits are used
    # instead of the correct 6, and we can remove the extra zeros
    # to get a valid ID
    else:
        short_id = mesh_id[0] + mesh_id[4:]
        name = mesh_client.get_mesh_name(short_id, offline=True)
        if name:
            return short_id
    # Another pattern is one where the MeSH ID is simply invalid but the
    # corresponding MeSH term allows us to get a valid ID via reverse
    # ID lookup - done here as grounding just to not have to assume
    # perfect / up to date naming conventions in the source data.
    if mesh_term:
        matches = gilda.ground(mesh_term, namespaces=["MESH"])
        if len(matches) == 1:
            for k, v in matches[0].get_groundings():
                if k == "MESH":
                    return v
    return None


def ground_condition(condition: str) -> list[gilda.grounder.ScoredMatch]:
    """
    Ground a condition string to a standard ontology.

    Parameters
    ----------
    condition : str
        The condition to ground.

    Returns
    -------
    list[gilda.grounder.ScoredMatch]
        The grounded condition.
    """
    matches = gilda.ground(condition)
    matches = [
        match
        for match in matches
        if match.term.db in {"MESH", "DOID", "EFO", "HP", "GO"}
    ]
    if matches:
        return matches[0].term
    return None


def ground_drug(drug: str) -> list[gilda.grounder.ScoredMatch]:
    """
    Ground a drug string to a standard ontology.

    Parameters
    ----------
    drug : str
        The drug to ground.
    """
    matches = gilda.ground(drug)
    if matches:
        return matches[0].term
    return None


def standardize(prefix: str, identifier: str) -> tuple[str, str]:
    """Get a standardized prefix and identifier.

    Parameters
    ----------
    prefix : str
        The prefix to standardize.
    identifier : str
        The identifier to standardize.

    Returns
    -------
    tuple[str, str] :
        A tuple of the standardized prefix and identifier.
    """

    standard_name, db_refs = standardize_name_db_refs({prefix: identifier})
    db_ns, db_id = get_grounding(db_refs)
    if db_ns is None or db_id is None:
        return prefix, identifier
    return db_ns, db_id


class Transformer:
    """
    Transform ClinicalTrials.gov data into nodes and edges for a graph database.

    Attributes
    ----------
    has_trial_cond_ns : list
        The namespaces of conditions in trials.
    has_trial_cond_id : list
        The IDs of conditions in trials.
    has_trial_nct : list
        The NCT IDs of trials.
    tested_in_int_ns : list
        The namespaces of interventions tested in trials.
    tested_in_int_id : list
        The IDs of interventions tested in trials.
    tested_in_nct : list
        The NCT IDs of trials.
    problematic_mesh_ids : list
        The problematic MeSH IDs.
    df : DataFrame
        The DataFrame to transform.
    """

    def __init__(self):
        self.has_trial_cond_ns = []
        self.has_trial_cond_id = []
        self.has_trial_nct = []
        self.tested_in_int_ns = []
        self.tested_in_int_id = []
        self.tested_in_nct = []

        self.problematic_mesh_ids = []

        self.df = pd.DataFrame()

    def clean_data_values(self) -> None:
        """Clean up values in DataFrame"""

        self.df["start_year"] = self.df["StartDate"].apply(_get_start_year).astype("Int64")
 
        # randomized, Non-Randomized
        self.df["randomized"] = self.df["DesignAllocation"].map(
            lambda s: "true" if pd.notna(s) and s == "Randomized" else "false"
        )

        # Indicate if the start_year is anticipated or not
        self.df["start_year_anticipated"] = self.df["StartDateType"].map(
            lambda s: "true" if pd.notna(s) and s == "Anticipated" else "false"
        )

        # Map the phase info for trial to integer (-1 for unknown)
        self.df["Phase"] = self.df["Phase"].apply(_get_phase)

        # Create a Neo4j compatible list of references
        self.df["ReferencePMID"] = self.df["ReferencePMID"].map(
            lambda s: ";".join(f"PUBMED:{pubmed_id}" for pubmed_id in s.split("|")),
            na_action="ignore",
        )
    
    # def get_nodes(self):
    def get_nodes(self) -> Iterator:
        """
        Get nodes from the DataFrame.
        """
        nctid_to_data = {}
        yielded_nodes = set()
        for _, row in tqdm(self.df.iterrows(), total=len(self.df)):
            nctid_to_data[row["NCTId"]] = {
                "study_type": or_na(row["StudyType"]),  # observational, interventional
                "randomized:boolean": row["randomized"],
                "status": or_na(row["OverallStatus"]),  # Completed, Active, Recruiting
                "phase:int": row["Phase"],
                "why_stopped": or_na(row["WhyStopped"]),
                "start_year:int": or_na(row["start_year"]),
                "start_year_anticipated:boolean": row["start_year_anticipated"],
            }

            found_disease_gilda = False
            for condition in str(row["Condition"]).split("|"):
                cond_term = ground_condition(condition)
                if cond_term:
                    self.has_trial_nct.append(row["NCTId"])
                    self.has_trial_cond_ns.append(cond_term.db)
                    self.has_trial_cond_id.append(cond_term.id)
                    found_disease_gilda = True
                    if (cond_term.db, cond_term.id) not in yielded_nodes:
                        yield Dict(
                            db_ns=cond_term.db,
                            db_id=cond_term.id,
                            labels=["BioEntity"],
                            data=Dict(name=cond_term.entry_name),
                        )
                        yielded_nodes.add((cond_term.db, cond_term.id))
            if not found_disease_gilda and not isna(row["ConditionMeshId"]):
                for mesh_id, mesh_term in zip(
                    row["ConditionMeshId"].split("|"),
                    row["ConditionMeshTerm"].split("|")
                ):
                    correct_mesh_id = get_correct_mesh_id(mesh_id, mesh_term)
                    if not correct_mesh_id:
                        self.problematic_mesh_ids.append((mesh_id, mesh_term))
                        continue
                    db_ns, db_id = standardize("MESH", correct_mesh_id)
                    stnd_node = Dict(
                        db_ns=db_ns,
                        db_id=db_id,
                        labels=["BioEntity"],
                        data={}
                    )
                    node_ns, node_id = stnd_node["db_ns"], stnd_node["db_id"]
                    self.has_trial_nct.append(row["NCTId"])
                    self.has_trial_cond_ns.append(node_ns)
                    self.has_trial_cond_id.append(node_id)
                    if (node_ns, node_id) not in yielded_nodes:
                        yield stnd_node
                        yielded_nodes.add((node_ns, node_id))

            # We first try grounding the names with Gilda, if any match, we
            # use it, if there are no matches, we go by provided MeSH ID
            found_drug_gilda = False
            for int_name, int_type in zip(
                str(row["InterventionName"]).split("|"),
                str(row["InterventionType"]).split("|")
            ):
                if int_type == "Drug":
                    drug_term = ground_drug(int_name)
                    if drug_term:
                        self.tested_in_int_ns.append(drug_term.db)
                        self.tested_in_int_id.append(drug_term.id)
                        self.tested_in_nct.append(row["NCTId"])
                        if (drug_term.db, drug_term.id) not in yielded_nodes:
                            yield Dict(
                                db_ns=drug_term.db,
                                db_id=drug_term.id,
                                labels=["BioEntity"],
                                data=Dict(name=drug_term.entry_name)
                            )
                            found_drug_gilda = True
                            yielded_nodes.add((drug_term.db, drug_term.id))
            # If there is no Gilda grounding but there are some MeSH IDs given
            if not found_drug_gilda and not isna(row["InterventionMeshId"]):
                for mesh_id, mesh_term in zip(
                    row["InterventionMeshId"].split("|"),
                    row["InterventionMeshTerm"].split("|"),
                ):
                    correct_mesh_id = get_correct_mesh_id(mesh_id, mesh_term)
                    if not correct_mesh_id:
                        self.problematic_mesh_ids.append((mesh_id, mesh_term))
                        continue
                    db_ns, db_id = standardize("MESH", correct_mesh_id)
                    stnd_node = Dict(
                        db_ns=db_ns,
                        db_id=db_id,
                        labels=["BioEntity"],
                        data={}
                    )
                    node_ns, node_id = stnd_node["db_ns"], stnd_node["db_id"]
                    self.tested_in_int_ns.append(node_ns)
                    self.tested_in_int_id.append(node_id)
                    self.tested_in_nct.append(row["NCTId"])
                    if (node_ns, node_id) not in yielded_nodes:
                        yield stnd_node
                        yielded_nodes.add((node_ns, node_id))

        for nctid in set(self.tested_in_nct) | set(self.has_trial_nct):
            if ("CLINICALTRIALS", nctid) not in yielded_nodes:
                yield Dict(
                    db_ns="CLINICALTRIALS",
                    db_id=nctid,
                    labels=["ClinicalTrial"],
                    data=nctid_to_data[nctid],
                )
                yielded_nodes.add(("CLINICALTRIALS", nctid))

        logger.info(
            "Problematic MeSH IDs: %s"
            % str(Counter(self.problematic_mesh_ids).most_common())
        )

    def get_edges(self):
        """
        Get edges from the DataFrame and the transformed data.
        """
        added = set()
        for cond_ns, cond_id, target_id in zip(
            self.has_trial_cond_ns, self.has_trial_cond_id, self.has_trial_nct
        ):
            if (cond_ns, cond_id, target_id) in added:
                continue
            added.add((cond_ns, cond_id, target_id))
            yield Dict(
                source_ns=cond_ns,
                source_id=cond_id,
                target_ns="CLINICALTRIALS",
                target_id=target_id,
                rel_type="has_trial",
                data={}
            )
        added = set()
        for int_ns, int_id, target_id in zip(
            self.tested_in_int_ns, self.tested_in_int_id, self.tested_in_nct
        ):
            if (int_ns, int_id, target_id) in added:
                continue
            added.add((int_ns, int_id, target_id))
            yield Dict(
                source_ns=int_ns,
                source_id=int_id,
                target_ns="CLINICALTRIALS",
                target_id=target_id,
                rel_type="tested_in",
                data={}
            )
