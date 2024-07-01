import logging

import pandas as pd
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import bioregistry
import gilda
import gilda.ner

from .config import Config
from .store import store_dataframe_as_flat_file


logger = logging.getLogger(__name__)


class Processor:
    """
    Processes transformed WHO data into nodes and edges.

    Attributes
    ----------
    df : DataFrame
        Transformed WHO data
    config : Config
        Configuration for WHO data processing
    counter : dict
        Counts of mapped and unmapped entities
    nodes_df : DataFrame
        Nodes DataFrame
    mappings_df : DataFrame
        Mappings DataFrame
    matches_dfs : dict
        Named entity recognition DataFrames
    full_df : DataFrame
        Full DataFrame

    Parameters
    ----------
    transformed_data : DataFrame
        Transformed WHO data
    config : Config
        Configuration for WHO data processing
    """
    def __init__(self, transformed_data: pd.DataFrame, config: Config):
        self.df = transformed_data
        self.config = config
        self.counter = {True: [], False: []}
        self.nodes_df = None
        self.mappings_df = None
        self.matches_dfs = {}
        self.full_df = None

    def process_nodes(self) -> None:
        """Processes nodes from the transformed data and stores them in the nodes_df DataFrame"""
        logger.info("Processing nodes")

        nodes_df = self.df[["curie", "name", "type"]].copy().sort_values("curie")
        nodes_df[":LABEL"] = nodes_df["curie"].map(lambda s: s.split(":")[0] + ";trial")
        nodes_df.rename(columns={"curie": "curie:ID"}, inplace=True)
        clinicaltrialsgov_idx = nodes_df["curie:ID"].map(lambda s: s.startswith("clinicaltrials:"))
        self.nodes_df = nodes_df[~clinicaltrialsgov_idx]  # don't re-add these

    def process_mappings(self) -> None:
        """Processes mappings from the transformed data and stores them in the mappings_df DataFrame"""
        logger.info("Processing mappings")

        curie_to_name = dict(self.df[["curie", "name"]].values)

        mapping_rows = []
        for curie, _name, mapping_curies in self.df[["curie", "name", "mappings"]].values:
            if not isinstance(mapping_curies, list):
                continue
            for mapping_curie in mapping_curies:
                mapped_name = curie_to_name.get(mapping_curie)
                self.counter[mapped_name is not None].append(mapping_curie)
                mapping_rows.append(
                    (curie, mapping_curie, "related_trial", "debio:0000040", self.config.source_key)
                )

        n_unmapped = len(self.counter[False])
        n_mapped = len(self.counter[True])
        total = n_unmapped + n_mapped
        logging.info(
            f"Could not map {n_unmapped:,}/{total:,} ({n_unmapped/total:.1%}). Some example unmapped: {self.counter[False][:5]}"
        )

        self.mappings_df = pd.DataFrame(
            mapping_rows, columns=[":START_ID", ":END_ID", ":TYPE", "curie", self.config.source_key]
        ).sort_values([":START_ID", ":END_ID"])

    def process_matches(self) -> None:
        """
        Processes named entity recognition from the transformed data and stores them in the matches_dfs dictionary.

        The keys are the columns to process and the values are the DataFrames of named entities recognized in those columns.
        Stores the full DataFrame in full_df and writes it to disk as compressed TSV.
        """
        logger.info("Processing matches")
        for curie in self.counter[False][:5]:
            logging.info(f"https://bioregistry.io/{curie}")

        config = [
            (
                "conditions",
                ["doid", "mondo", "go", "MESH"],
                "has_condition",
                "debio:0000036",
                gilda.annotate,
                {"doid:4"},
            ),
            (
                "interventions",
                None,
                "has_intervention",
                "debio:0000036",
                gilda.ner.annotate,
                set()
            ),
            # "primary_outcome",
            # "secondary_outcome",
        ]

        logger.info("warming up grounder")
        gilda.annotate("stuff")
        logger.info("done warming up grounder")
        logger.info("Processing columns")
        for column, namespaces, rtype, rcurie, annotate_fn, skip in config:
            rows = []
            for curie, cells in tqdm(
                self.df[["curie", column]].values,
                unit="trial",
                unit_scale=True,
                desc=f"Annotating {column}",
            ):
                if cells is None:
                    continue
                if isinstance(cells, str):
                    cells = [cells]
                for cell in cells:
                    if not cell or pd.isna(cell):
                        continue
                    with logging_redirect_tqdm():
                        annotations = annotate_fn(cell)
                    for _text, match, start, end in annotations:
                        if namespaces is not None and match.term.db not in namespaces:
                            continue
                        match_term_curie = bioregistry.curie_to_str(match.term.db, match.term.id)
                        if match_term_curie in skip:
                            continue
                        rows.append(
                            (
                                curie,
                                match_term_curie,
                                match.term.entry_name,
                                rtype,
                                rcurie,
                                cell,
                                start,
                                end,
                                self.config.source_key,
                            )
                        )
            NER_COLUMNS = [
                ":START_ID",
                ":END_ID",
                "target_name",
                ":TYPE",
                "curie",
                "text",
                "start:int",
                "end:int",
                self.config.source_key,
            ]
            tqdm.write(f"Recognized {len(rows):,} named entities in the {column} column")
            self.matches_dfs[column] = matches_df = pd.DataFrame(rows, columns=NER_COLUMNS).sort_values(
                NER_COLUMNS
            )

            output_path = self.config.ner_dir_path.joinpath(f"ner_{column}.tsv.gz")
            output_sample_path = self.config.sample_dir_path.joinpath(f"ner_{column}_sample.tsv")
            store_dataframe_as_flat_file(matches_df, output_path, "\t", False)
            store_dataframe_as_flat_file(matches_df.head(100), output_sample_path, "\t", False)

    def process_full_dataframe(self) -> None:
        """Processes the full DataFrame by concatenating the mappings DataFrame and the DataFrames of named entities recognized in the columns."""
        logger.info("Processing full dataframe")
        self.full_df = pd.concat([self.mappings_df, *self.matches_dfs.values()]).sort_values(":START_ID")
        self.full_df = self.full_df[[":START_ID", ":END_ID", ":TYPE", "curie", self.config.source_key]]
        self.full_df = self.full_df.drop_duplicates()

    def process_who_data(self) -> None:
        """Processes WHO data by calling the process_nodes, process_mappings, process_matches, and process_full_dataframe methods."""
        logger.info("Processing WHO data")
        self.process_nodes()
        store_dataframe_as_flat_file(self.nodes_df, self.config.nodes_path, "\t", False)
        self.process_mappings()
        store_dataframe_as_flat_file(self.mappings_df, self.config.mappings_path, "\t", False)
        self.process_matches()
        self.process_full_dataframe()
        store_dataframe_as_flat_file(self.full_df, self.config.edges_path, "\t", False)
