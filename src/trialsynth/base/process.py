import re
import csv
import gzip
import logging
from pathlib import Path
from typing import Callable, Dict, Optional

import click
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from . import store
from .config import Config
from .fetch import Fetcher
from ..base.ground import Grounder
from .models import Condition, Edge, Trial, PublicationEdge
from .transform import Transformer
from .validate import Validator
from ..base.extract.build_pubmed_nct_links import PMID_NCT_LINKS

logger = logging.getLogger(__name__)


NCT_EXTRACT_RE = re.compile(r"NCT\s*(\d{8})", re.IGNORECASE)


def run_processor(
    func: Callable[[bool, bool, bool], None]
) -> Callable[[bool, bool, bool], None]:
    """
    A decorator that wraps a function for running a processor.

    Parameters
    ----------
    func : Callable[[bool, bool, bool], None]
        The function to be wrapped.

    Returns
    -------
    Callable[[bool, bool, bool], None]
        The wrapped function with Click command options.
    """

    @click.command()
    @click.option(
        "-r",
        "--reload",
        is_flag=True,
        default=False,
        help="Reload data from the API",
    )
    @click.option(
        "-s",
        "--store-samples",
        is_flag=True,
        default=False,
        help="Store samples",
    )
    @click.option(
        "-v",
        "--validate",
        is_flag=True,
        default=False,
        help="Validate the data",
    )
    def wrapper(reload: bool, store_samples: bool, validate: bool):
        return func(reload, store_samples, validate)

    return wrapper


class Processor:
    """Processes registry data using Config and Fetcher objects to graph data.

    Attributes
    ----------
    config : Config
        User-mutable properties of registry data processing
    fetcher : Fetcher
        Fetches registry data from the REST API or a saved file
    condition_grounder : Grounder
        Grounds conditions using a condition preprocessor
    intervention_grounder : Grounder
        Grounds interventions using an intervention preprocessor
    conditions : list[BioEntity]
        List of conditions from the trials to be grounded
    interventions : list[BioEntity]
        List of interventions from the trials to be grounded
    edges : list[Edge]
        List of edges connecting trials to conditions and interventions
    reload_api_data : bool
        Whether to reload the API data
    store_samples : bool
        Whether to store samples of the data

    Parameters
    ----------
    config : Config
        User-mutable properties of registry data processing
    fetcher : Fetcher
        Fetches registry data from the REST API or a saved file
    transformer : Transformer
        Serializes data into strings for storage
    condition_grounder : Grounder
        Grounds conditions into CURIEs
    intervention_grounder : Grounder
        Grounds interventions into CURIEs
    reload_api_data : bool
        Whether to reload the API data (default: False).
    store_samples : bool
        Whether to store samples of the data (default: False).
    validate : bool
        Whether to validate the data (default: True).
    """

    def __init__(
        self,
        config: Config,
        fetcher: Fetcher,
        transformer: Transformer,
        condition_grounder: Grounder,
        intervention_grounder: Grounder,
        validator: Validator,
        reload_api_data: bool = False,
        store_samples: bool = False,
        validate: bool = True,
    ):
        self.config = config

        self.fetcher = fetcher

        self.transformer = transformer
        self.validator = validator

        self.trials: list[Trial] = []

        self.curie_to_trial: Dict[str, Trial] = {}

        # Grounders for conditions and interventions
        self.condition_grounder: Grounder = condition_grounder
        self.intervention_grounder: Grounder = intervention_grounder

        self.entities: dict[type, list] = {}

        self.edges: list[Edge] = []
        self.trial_publication_edges: list[PublicationEdge] = []

        self.reload_api_data: bool = reload_api_data
        self.store_samples: bool = store_samples
        self.validate: bool = validate

    def run(self, max_pages=None):
        """Processes registry data into a graph structure."""
        self.fetcher.get_api_data(reload=self.reload_api_data, max_pages=max_pages)
        self.trials = self.fetcher.raw_data
        #  ground and process bioentities for storing
        self.get_bioentities()
        self.process_bioentities()

        # remove duplicate trial entries, using this instead of curie_trial_dict to avoid accessing hash structure
        # create edges
        self.create_edges()

        # save processed data
        self.save_data()

        # validate data
        if self.validate:
            self.validate_data()

    def get_bioentities(self):
        """Extracts bioentities from trials and creates a dictionary of trial CURIEs to trials."""

        for trial in self.trials:

            self.curie_to_trial[trial.curie] = trial

            for entity in trial.entities:
                if type(entity) not in self.entities.keys():
                    self.entities[type(entity)] = []

                self.entities[type(entity)].append(entity)

            trial.entities = []

    def process_bioentities(self):
        """Processes bioentities by grounding them."""
        logger.info("Warming up grounders...")
        self.condition_grounder.ground("stuff")
        self.intervention_grounder.ground("stuff")
        logger.info("Done.")

        for ent_type, entities, grounder in zip(
            self.entities.keys(),
            self.entities.values(),
            [self.condition_grounder, self.intervention_grounder]
        ):
            entity_type = ent_type.__name__.lower()
            entity_iter = tqdm(entities, desc=f'Grounding {entity_type}s', unit=entity_type, unit_scale=True)

            for entity in entity_iter:
                with logging_redirect_tqdm():
                    trial = self.curie_to_trial[entity.origin]
                    context = trial.title
                    if trial.brief_summary:
                        context += "\n" + trial.brief_summary
                    if trial.detailed_description:
                        context += "\n" + trial.detailed_description

                    entities = list(grounder(entity, context=context))

                    trial.entities.extend(entities)

    def create_edges(self):
        """Creates edges connecting trials to related bioentities and pmids"""
        with gzip.open(PMID_NCT_LINKS, "rt") as f:
            csv_reader = csv.reader(f, delimiter="\t")
            _ = next(csv_reader)
            pubmed_trial_links = set(tuple(row) for row in csv_reader)

        for trial in tqdm(
            self.trials,
            desc="Generating edges from trial",
            unit="trial",
            unit_scale=True,
        ):
            # Group conditions and interventions of same grounding together, and
            # create edges from trial to each unique grounded entity with a list
            # of the sources of that grounding e.g., ['mesh', 'gilda']
            condition_sources = {}
            intervention_sources = {}
            for cond in trial.conditions:
                if cond.curie not in condition_sources:
                    condition_sources[cond.curie] = []
                condition_sources[cond.curie].append(cond.grounding_source)
            for intv in trial.interventions:
                if intv.curie not in intervention_sources:
                    intervention_sources[intv.curie] = []
                intervention_sources[intv.curie].append(intv.grounding_source)

            # Create intervention and condition edges
            added_conditions = set()
            added_interventions = set()
            for entity in trial.entities:
                if isinstance(entity, Condition):
                    if entity.curie in added_conditions:
                        continue
                    added_conditions.add(entity.curie)
                    grounding_sources = condition_sources.get(entity.curie, [])
                else:
                    if entity.curie in added_interventions:
                        continue
                    added_interventions.add(entity.curie)
                    grounding_sources = intervention_sources.get(
                        entity.curie, []
                    )

                self.edges.append(
                    Edge(
                        trial,
                        entity,
                        self.config.registry,
                        grounding_sources=grounding_sources,
                    )
                )

            # Create trial - publication edges from trial data
            for pmid, ref_type in trial.references:
                self.trial_publication_edges.append(
                    PublicationEdge(
                        trial=trial.curie,
                        publication=pmid,
                        source="clinicaltrials.gov",
                        ref_type=ref_type,
                    )
                )

        def _extract_nct_ids(raw: str) -> list[str]:
            # Return canonical NCT######## IDs found in a raw accession string
            return [f"NCT{digits}" for digits in NCT_EXTRACT_RE.findall(raw)]

        # Create trial - publication edges from PubMed XML data
        for pmid, nct_id in tqdm(
            pubmed_trial_links,
            desc="Processing PubMed data",
            unit="publication",
            unit_scale=True,
        ):
            nct_ids = _extract_nct_ids(nct_id)
            for nct_id in nct_ids:
                self.trial_publication_edges.append(
                    PublicationEdge(
                        trial=nct_id,
                            publication=pmid,
                            source="pubmed",
                        )
                    )

    def save_trial_data(
        self, path: Path, sample_path: Optional[Path] = None
    ) -> None:
        """Saves processed trial data to a compressed tsv file.

        Parameters
        ----------
        path : Path
            The path to save the processed trial data
        sample_path
            The path to save the sample trial data (default: None).

        Returns
        -------
        None
        """
        data = [
            self.transformer.flatten_trial_data(trial)
            for trial in self.curie_to_trial.values()
        ]

        headers = [
            "curie:CURIE",
            "title:string",
            "official_title:string",
            "brief_summary:string",
            "detailed_description:string",
            "labels:LABEL[]",
            "design:DESIGN",
            "conditions:CURIE[]",
            "interventions:CURIE[]",
            "primary_outcome:OUTCOME[]",
            "secondary_outcome:OUTCOME[]",
            "secondary_ids:CURIE[]",
            "source_registry:string",
            "phases:PHASE[]",
            "start_year:integer",
            "start_year_anticipated:boolean",
            "primary_completion_year:integer",
            "primary_completion_year_type:string",
            "completion_year:integer",
            "completion_year_type:string",
            "last_update_submit_year:integer",
            "status:string",
            "why_stopped:string",
            "references:string[]",
        ]

        store.save_data_as_flatfile(
            data,
            path=path,
            headers=headers,
            sample_path=sample_path,
            num_samples=self.config.num_sample_entries,
        )

    def save_bioentities(
        self, path: Path, sample_path: Optional[Path] = None
    ) -> None:
        """Saves processed bioentities to a compressed tsv file.

        Parameters
        ----------
        path : Path
            The path to save the processed bioentities
        sample_path
            The path to save the sample bioentities (default: None).

        Returns
        -------
        None
        """
        entities = set()
        for trial in self.trials:
            for entity in trial.entities:
                flat_entity = self.transformer.flatten_bioentity(entity)
                entities.add(flat_entity)
        # Sort entities by entity CURIE and trial CURIE
        entities = sorted(entities, key=lambda x: (x[0], x[-1]))
        store.save_data_as_flatfile(
            entities,
            path=path,
            headers=[
                "curie:CURIE",
                "term:string",
                "labels:LABEL[]",
                "source_registry:string",
                "trial:CURIE",
            ],
            sample_path=sample_path,
            num_samples=self.config.num_sample_entries,
        )

    def save_edges(self, path: Path, sample_path: Optional[Path] = None):
        """Saves processed edges to a compressed tsv file.

        Parameters
        ----------
        path : Path
            The path to save the processed edges
        sample_path
            The path to save the sample edges (default: None).

        Returns
        -------
        None
        """
        edges = [self.transformer.flatten_edge(edge) for edge in self.edges]

        store.save_data_as_flatfile(
            list(set(edges)),  # Remove duplicate edges
            path=path,
            headers=[
                "from:CURIE",
                "to:CURIE",
                "rel_type:string",
                "source_registry:string",
                "grounding_sources:string[]",
            ],
            sample_path=sample_path,
            num_samples=self.config.num_sample_entries,
        )

    def save_trial_publication_edges(self, path: Path, sample_path: Optional[Path] = None):
        """Saves processed trial publication edges to a compressed tsv file

        Parameters
        ----------
        path :
            The path to save the processed trial publication edges
        sample_path :
            If provided, save a sample of the processed trial publication edges
            to this path. Defaults to None.
        """
        edges = [
            self.transformer.flatten_trial_publication_edge(edge)
            for edge in self.trial_publication_edges
        ]

        store.save_data_as_flatfile(
            # Remove duplicates and sort edges by trial and publication
            sorted(set(edges), key=lambda x: (x[0], x[1])),
            path=path,
            headers=[
                "trial_id",
                "pmid",
                "rel_type",
                "source",
                "ref_type",
            ],
            sample_path=sample_path,
            num_samples=self.config.num_sample_entries,
        )

    def save_data(self):
        """Saves processed data to compressed tsv files."""

        if not self.config.sample_dir.is_dir():
            self.config.sample_dir.mkdir()

        # save processed trial data to compressed tsv
        logger.info(
            f"Serializing and storing processed trial data to {self.config.trials_path}"
        )
        self.save_trial_data(
            self.config.trials_path,
            sample_path=(
                self.config.trials_sample_path if self.store_samples else None
            ),
        )

        # save processed bioentity data to compressed tsv
        logger.info(
            f"Serializing and storing grounded bioentities to {self.config.bio_entities_path}"
        )
        self.save_bioentities(
            self.config.bio_entities_path,
            sample_path=(
                self.config.bio_entities_sample_path
                if self.store_samples
                else None
            ),
        )

        # save edges to compressed tsv
        logger.info(
            f"Serializing and storing edges to {self.config.edges_path}"
        )
        self.save_edges(
            self.config.edges_path,
            sample_path=(
                self.config.edges_sample_path if self.store_samples else None
            ),
        )

        # save trial - pmid relations as a compressed tsv
        logger.info(
            f"Serializing and storing trial-publication edges to "
            f"{self.config.trial_publication_edges_path}"
        )
        self.save_trial_publication_edges(
            self.config.trial_publication_edges_path,
        )

    def validate_data(self):
        """Validates the processed data using the Validator object."""
        logger.info("Validating trial data.")
        self.validator(self.config.trials_path)
        logger.info("Validating bioentity data.")
        self.validator(self.config.bio_entities_path)
        logger.info("Validating edge data.")
        self.validator(self.config.edges_path)
