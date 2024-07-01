import logging
from typing import Literal, Any, Optional, Mapping, Iterable

from indra.statements.validate import assert_valid_db_refs, assert_valid_evidence
from indra.statements import Evidence


# See https://neo4j.com/docs/operations-manual/4.4/tools/neo4j-admin/neo4j-admin-import/#import-tool-header-format-properties
# and
# https://neo4j.com/docs/api/python-driver/current/api.html#data-types
# for available data types.
NEO4J_DATA_TYPES = (
    "int",
    "long",
    "float",
    "double",
    "boolean",
    "byte",
    "short",
    "char",
    "string",
    "point",
    "date",
    "localtime",
    "time",
    "localdatetime",
    "datetime",
    "duration",
    # Used in node files
    "ID",
    "LABEL",
    # Used in relationship files
    "START_ID",
    "END_ID",
    "TYPE",
)

DataTypes = Literal[
    "int",
    "long",
    "float",
    "double",
    "boolean",
    "byte",
    "short",
    "char",
    "string",
    "point",
    "date",
    "localtime",
    "time",
    "localdatetime",
    "datetime",
    "duration",
    "ID",
    "LABEL",
    "START_ID",
    "END_ID",
    "TYPE",
]


logger = logging.getLogger(__name__)


def get_nodes_by_type(nodes_by_type: dict, node_type: str) -> list:
    """Retrieve nodes of a specific type from a node dictionary.

    Parameters
    ----------
    nodes_by_type : dict
        A dictionary where keys are node types and values are lists of nodes.

    node_type : str
        The type of node to retrieve.

    Returns
    -------
    list
        A list of nodes of the specified type sorted by namespace and ID.
    """
    if node_type not in nodes_by_type:
        logger.warning(f"Node type '{node_type}' not found in dictionary. Returning empty list.")
        return []
    nodes = sorted(nodes_by_type[node_type], key=lambda x: (x["db_ns"], x["db_id"]))
    return nodes


    
def validate_node_data(processor_name:str, nodes: list[dict]) -> None:
    """Validate the node data before yielding them.

    Parameters
    ----------
    processor_name : str
        The name of the processor.

    nodes : list[dict]
        The nodes to validate.
    """

    # Get the metadata from the nodes
    metadata = sorted(set(key for node in nodes for key in node.data))
    header = "id:ID", ":LABEL", *metadata
    
    # Validate the headers
    try:
        validate_headers(header)
    except TypeError:
        logger.exception(f"Bad node data type in header for {processor_name}")
        raise

    # Validate the nodes
    try:
        validate_nodes(nodes, metadata)
    except (UnknownTypeError, DataTypeError):
        logger.exception(f"Bad node data type in node data values for {processor_name}")
        raise


def validate_edge_data(processor_name:str, edges: list[dict]) -> None:
    """Validate the edge data before yielding them.

    Parameters
    ----------
    processor_name : str
        The name of the processor.
    edges : list[dict]
        The edges to validate.
    """
    metadata = sorted(set(key for edge in edges for key in edge.data))
    header = ":START_ID", ":END_ID", ":TYPE", *metadata

    try:
        validate_headers(header)
    except TypeError as e:
        logger.error(f"Bad edge data type in header for {self.name}")
        raise e

    try:
        validate_edges(edges, metadata)
    except (UnknownTypeError, DataTypeError) as e:
        logger.error(f"Bad edge data type in edge data values for {processor_name}")
        raise e

def assert_valid_node(
    db_ns: str,
    db_id: str,
    data: Optional[Mapping[str, Any]] = None,
    check_data: bool = False,
) -> Optional[dict[str, bool]]:
    if db_ns == "indra_evidence":
        if data and data.get("evidence:string"):
            ev = Evidence._from_json(json.loads(data["evidence:string"]))
            assert_valid_evidence(ev)
    else:
        assert_valid_db_refs({db_ns: db_id})

    if check_data and data:
        checked_keys = {}
        for key, value in data.items():
            # Skip None values, mark as not checked
            if value is None:
                checked_keys[key] = False
                continue
            if ":" in key:
                dtype = key.split(":")[1]
            else:
                # If no data type is specified, string is assumed by Neo4j
                dtype = "string"
            data_validator(dtype, value)

            checked_keys[key] = True

        return checked_keys

    
def validate_nodes(
    nodes: Iterable[dict],
    header: Iterable[str],
    check_all_data: bool = True,
) -> None:
    """Validate the nodes before yielding them.

    Parameters
    ----------
    nodes : Iterable[dict]
        The nodes to validate.
    header : Iterable[str]
        The header of the output Neo4j ingest file.
    check_all_data : bool
        If True, check all data keys in the nodes. If False, stop checking
        when all data keys have been checked. Default: True

    Raises
    ------
    UnknownTypeError
        If a data type is not recognized.
    DataTypeError
        If a data type does not match the value set in the header.
    """
    checked_headers = {key: False for key in header}
    for idx, node in enumerate(nodes):
        check_data = not all(checked_headers.values()) or check_all_data
        try:
            checked_fields = assert_valid_node(
                node.db_ns, node.db_id, node.data, check_data
            )
            if checked_fields:
                for key, checked in checked_fields.items():
                    if checked:
                        checked_headers[key] = True

            # Check if this was the iteration when all headers were checked
            if check_data and all(checked_headers.values()) and not check_all_data:
                logger.info(f"All node data keys checked at index {idx}. "
                            f"Skipping the rest")

        except (UnknownTypeError, DataTypeError) as e:
            logger.error(f"{idx}: {node} - {e}")
            logger.error("Bad node data type(s) detected")
            raise e
        except Exception as e:
            logger.info(f"{idx}: {node} - {e}")
            continue

    
def validate_edges(
    relations: Iterable[dict],
    header: Iterable[str],
    check_all_data: bool = True
) -> None:
    """Validate the relations before yielding them.

    Parameters
    ----------
    relations : Iterable[dict]
        The relations to validate.
    header : Iterable[str]
        The header of the output Neo4j ingest file.
    check_all_data : bool
        If True, check all data keys in the relations. If False, stop checking
        when all data keys have been checked. Default: True

    Raises
    ------
    UnknownTypeError
        If a data type is not recognized.
    DataTypeError
        If a data type does not match the value set in the header.
    """

    checked_headers = {key: False for key in header}
    for idx, rel in enumerate(relations):
        try:
            check_data = not all(checked_headers.values()) or check_all_data
            checked_fields = assert_valid_node(
                rel.source_ns, rel.source_id, rel.data, check_data
            )
            assert_valid_node(rel.target_ns, rel.target_id)
            if checked_fields:
                for key, checked in checked_fields.items():
                    if checked:
                        checked_headers[key] = True

            # Check if this was the iteration when all headers were checked
            if check_data and all(checked_headers.values()) and not check_all_data:
                logger.info(f"All relation data keys checked at index {idx}. "
                            f"Skipping the rest")
            yield rel
        except (UnknownTypeError, DataTypeError) as e:
            logger.error(f"{idx}: {rel} - {e}")
            logger.error("Bad relation data type(s) detected")
            raise e
        except Exception as e:
            logger.info(f"{idx}: {rel} - {e}")
            continue

    
def validate_headers(headers: Iterable[str]) -> None:
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
    for header in headers:
        # If : is in the header and there is something after it check if
        # it's a valid data type
        if ":" in header and header.split(":")[1]:
            dtype = header.split(":")[1]

            # Strip trailing '[]' for array types
            if dtype.endswith("[]"):
                dtype = dtype[:-2]

            if dtype not in NEO4J_DATA_TYPES:
                raise TypeError(
                    f"Invalid header data type '{dtype}' for header {header}"
                )


class DataTypeError(TypeError):
    """Raised when a data value is not of the expected type"""


class UnknownTypeError(TypeError):
    """Raised when a data type is not recognized."""


def data_validator(data_type: str, value: Any):
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
    # None's are provided in the data dictionaries upon initial
    # node/relationship generation as a missing/null value. Once dumped,
    # the None's are converted to empty strings which is read in when nodes
    # are assembled. If we encounter a null value, there is no need to
    # validate it.
    null_data = {None, ""}
    if value in null_data:
        return

    if isinstance(value, str):
        value_list = value.split(";") if data_type.endswith("[]") else [value]
    else:
        value_list = [value]
    value_list = [val for val in value_list if val not in null_data]
    if not value_list:
        return
    data_type = data_type.rstrip("[]")
    if data_type == "int" or data_type == "long" or data_type == "short":
        for val in value_list:
            if isinstance(val, str):
                # Try to convert to int
                try:
                    val = int(val)
                except ValueError as e:
                    raise DataTypeError(
                        f"Data value '{val}' is of the wrong type to conform "
                        f"with Neo4j type {data_type}. Expected a value of "
                        f"type int, but got value of type str with value "
                        f"'{val}' instead."
                    ) from e
            if not isinstance(val, int):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type int, "
                    f"but got value of type {type(val)} instead."
                )
    elif data_type == "float" or data_type == "double":
        for val in value_list:
            if isinstance(val, str):
                # Try to convert to float
                try:
                    val = float(val)
                except ValueError as e:
                    raise DataTypeError(
                        f"Data value '{val}' is of the wrong type to conform "
                        f"with Neo4j type {data_type}. Expected a value of "
                        f"type float, but got value of type str with value "
                        f"'{val}' instead."
                    ) from e
            if not isinstance(val, float):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type float, "
                    f"but got value of type {type(val)} instead."
                )
    elif data_type == "boolean":
        for val in value_list:
            if not isinstance(val, str) or val not in ("true", "false"):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type str "
                    f"with literal value 'true' or 'false', but got value of "
                    f"type {type(val)} with value '{val}' instead."
                )
    elif data_type == "byte":
        for val in value_list:
            if not isinstance(val, (bytes, int)):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type bytes "
                    f"or int, but got value of type {type(val)} instead."
                )
    elif data_type == "char":
        for val in value_list:
            if not isinstance(val, str):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type str, "
                    f"but got value of type {type(val)} instead."
                )
    elif data_type == "string":
        for val in value_list:
            # Catch string representations of numbers
            if isinstance(val, (int, float)):
                try:
                    val = str(val)
                except ValueError as e:
                    raise DataTypeError(
                        f"Data value '{val}' is of the wrong type to conform "
                        f"with Neo4j type {data_type}. Expected a value of "
                        f"type str, int or float, but got value of type "
                        f"{type(val)} instead."
                    ) from e
            if not isinstance(val, str):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type str, "
                    f"int or float, but got value of type {type(val)} instead."
                )
    elif data_type == "point":
        raise NotImplementedError(
            "Neo4j point data type validation is not implemented"
        )
    # Todo: make stricter validation for dates and times:
    # https://neo4j.com/docs/cypher-manual/4.4/syntax/temporal/#cypher-temporal-instants
    elif data_type in [
        "date",
        "localtime",
        "time",
        "localdatetime",
        "datetime",
        "duration",
    ]:
        for val in value_list:
            if not isinstance(val, (str, int)):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type str "
                    f"or int, but got value of type {type(val)} instead."
                )
    elif data_type in ["ID", "LABEL", "START_ID", "END_ID", "TYPE"]:
        for val in value_list:
            if not isinstance(val, (str, int)):
                raise DataTypeError(
                    f"Data value '{val}' is of the wrong type to conform with "
                    f"Neo4j type {data_type}. Expected a value of type str "
                    f"or int, but got value of type {type(val)} instead."
                )
    else:
        raise UnknownTypeError(
            f"{data_type} is not recognized as a Neo4j data type."
        )
