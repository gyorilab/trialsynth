from collections import defaultdict
import csv
import logging
import gzip
from pathlib import Path
import pickle
from typing import Callable, Iterator

import pandas as pd
from tqdm import tqdm

from indra.databases import identifiers


logger = logging.getLogger(__name__)


class Storer:
    """Stores processed data to disk.

    Attributes
    ----------
    node_iterator : Callable[[], Iterator]
        Function to generate nodes from the transformed data
    node_types : list[str]
        Types of nodes
    node_types_to_paths : dict
        Paths to save nodes
    edges_path : Path
        Path to save edges
    edges_sample_path : Path
        Path to save sample edges

    Parameters
    ----------
    node_iterator : Callable[[], Iterator]
        Function to generate nodes from the transformed data
    node_types : list
        Types of nodes
    data_directory : Path
        Directory to save data
    """

    def __init__(self, node_iterator: Callable[[], Iterator], node_types: list[str], data_directory: Path, sample_directory: Path):
        self.node_iterator = node_iterator
        self.node_types = node_types
        self.node_types_to_paths = {
            node_type: (
                Path(data_directory, f"nodes_{node_type}.tsv.gz"),
                Path(data_directory, f"nodes_{node_type}.pkl"),
                Path(sample_directory, f"nodes_{node_type}_sample.tsv")
            )
            for node_type in node_types
        }
        self.edges_path = Path(data_directory, "edges.tsv.gz")
        self.edges_sample_path = Path(sample_directory, "edges_sample.tsv")

    def save_data(self, data: pd.DataFrame, path: Path) -> None:
        """Saves data to disk as a compressed TSV file.

        Parameters
        ----------
        data : DataFrame
            Data to save
        path : Path
            Path to save the data
        """
        logger.debug(f"Saving Clinicaltrials.gov data to {path}")
        try:
            data.to_csv(path, sep="\t", index=False, compression="gzip")
        except Exception:
            logger.exception(f"Could not save data to {path}")
            raise

    def save_node_data(self) -> None:
        """
        Save node data to disk as compressed TSV files.

        Raises
        ------
        RuntimeError
            If no nodes were generated for the graph
        """
        nodes_by_type = defaultdict(list)
        # Get all the nodes
        nodes = tqdm(
            self.node_iterator(),
            desc="Node generation",
            unit_scale=True,
            unit="node",
        )
        # Map the nodes to their types
        ix = 0
        for ix, node in enumerate(nodes):
            nodes_by_type[node.labels[0]].append(node)
        if ix == 0:
            raise RuntimeError(f"No nodes were generated for {self.name}")
        # Get the paths for each type of node and dump the nodes
        for node_type in nodes_by_type:
            nodes_path, nodes_indra_path, sample_path = self.node_types_to_paths.get(node_type)
            nodes = sorted(nodes_by_type[node_type], key=lambda x: (x.db_ns, x.db_id))
            with open(nodes_indra_path, "wb") as fh:
                pickle.dump(nodes, fh)
            self.dump_nodes_to_path(nodes, nodes_path, sample_path)

    def dump_nodes_to_path(
        self,
        nodes,
        nodes_path,
        sample_path=None,
        write_mode="wt"
    ):
        """Dump node data to a path as a compressed TSV file.

        Parameters
        ----------
        nodes : list
            List of nodes to dump
        nodes_path : Path
            Path to save the nodes
        sample_path : Path
            Path to save a sample of the nodes. Default: None
        write_mode : str
            Write mode for the file. Default: 'wt'
        """
        logger.info(f"Dumping node data into {nodes_path}")
        if sample_path:
            logger.info(f"Dumping sample node data into {sample_path}")
        metadata = sorted(set(key for node in nodes for key in node.data))
        header = "id:ID", ":LABEL", *metadata

        node_rows = (
            (
                norm_id(node.db_ns, node.db_id),
                ";".join(node.labels),
                *[node.data.get(key, "") for key in metadata],
            )
            for node in tqdm(nodes, desc="Node serialization", unit_scale=True)
        )

        with gzip.open(nodes_path, mode=write_mode) as node_file:
            node_writer = csv.writer(node_file, delimiter="\t")  # type: ignore
            # Only add header when writing to a new file
            if write_mode == "wt":
                node_writer.writerow(header)
            if sample_path:
                with sample_path.open("w") as node_sample_file:
                    node_sample_writer = csv.writer(node_sample_file, delimiter="\t")
                    node_sample_writer.writerow(header)
                    for _, node_row in zip(range(10), node_rows):
                        node_sample_writer.writerow(node_row)
                        node_writer.writerow(node_row)
            # Write remaining nodes
            node_writer.writerows(node_rows)

        
    # def dump_edges(self, rels, write_mode="wt"):
    def save_edge_data(self, rels, write_mode="wt"):
        """
        Save edge data to disk as a compressed TSV file.

        Parameters
        ----------
        rels : list
            List of edges to save
        write_mode : str
            Write mode for the file. Default: 'wt'
        """
        logger.info(f"Dumping edge data into {self.edges_path}...")

        metadata = sorted(set(key for rel in rels for key in rel.data))
        header = ":START_ID", ":END_ID", ":TYPE", *metadata

        rels = sorted(
            rels, key=lambda r: (r.source_ns, r.source_id, r.target_ns, r.target_id)
        )

        edge_rows = (
            (
                norm_id(rel.source_ns, rel.source_id),
                norm_id(rel.target_ns, rel.target_id),
                rel.rel_type,
                *[rel.data.get(key) for key in metadata],
            )
            for rel in tqdm(rels, desc="Edges", unit_scale=True)
        )

        with gzip.open(self.edges_path, mode=write_mode) as edge_file:
            edge_writer = csv.writer(edge_file, delimiter="\t")  # type: ignore

            # Only add header when writing to a new file
            if write_mode == "wt":
                edge_writer.writerow(header)
            if self.edges_sample_path:
                with self.edges_sample_path.open("w") as edge_sample_file:
                    edge_sample_writer = csv.writer(edge_sample_file, delimiter="\t")
                    edge_sample_writer.writerow(header)
                    for _, edge_row in zip(range(10), edge_rows):
                        edge_sample_writer.writerow(edge_row)
                        edge_writer.writerow(edge_row)
            # Write remaining edges
            edge_writer.writerows(edge_rows)


def norm_id(db_ns, db_id) -> str:
    """
    Normalize an identifier.

    Parameters
    ----------
    db_ns :
        The namespace of the identifier.
    db_id :
        The identifier.

    Returns
    -------
    str
        The normalized identifier.
    """

    identifiers_ns = identifiers.get_identifiers_ns(db_ns)
    identifiers_id = db_id
    if not identifiers_ns:
        identifiers_ns = db_ns.lower()
    else:
        ns_embedded = identifiers.identifiers_registry.get(identifiers_ns, {}).get(
            "namespace_embedded"
        )
        if ns_embedded:
            identifiers_id = identifiers_id[len(identifiers_ns) + 1 :]
    return f"{identifiers_ns}:{identifiers_id}"
