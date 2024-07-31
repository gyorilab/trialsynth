import copy
from typing import Iterator, Optional

import gilda
from indra.databases import mesh_client

from .models import BioEntity
from .util import CONDITION_NS, INTERVENTION_NS, must_override


class Grounder:
    """A callable class that grounds a BioEntity to a database identifier.

    Parameters
    ----------
    namespaces : Optional[list[str]]
        A list of namespaces to consider for grounding (default: None).

    Attributes
    ----------
    namespaces : Optional[list[str]]
        A list of namespaces to consider for grounding.
    """

    def __init__(self, namespaces: Optional[list[str]] = None):
        self.namespaces: Optional[list[str]] = namespaces

    @must_override
    def preprocess(self, entity: BioEntity, *kwargs) -> BioEntity:
        pass

    def ground(self, entity: BioEntity, context: Optional[str]) -> Iterator[BioEntity]:
        """Ground a BioEntity to a CURIE.

        Parameters
        ----------
        entity : BioEntity
            The BioEntity to ground.
        context : Optional[str]
            The context of the grounding to aid with disambiguation.

        Yields
        ------
        BioEntity
            The grounded BioEntity.
        """
        entity = self.preprocess(entity)
        if entity.ns and entity.ns.upper() == "MESH" and entity.id:
            if mesh_client.get_mesh_name(entity.id, offline=True):
                yield entity
            else:
                matches = gilda.ground(entity.term, namespaces=["MESH"])
                if matches:
                    match = matches[0].term
                    entity.ns, entity.id, entity.term = (
                        match.db,
                        match.id,
                        match.entry_name,
                    )
                    yield entity
        else:
            matches = gilda.ground(
                entity.term, namespaces=self.namespaces, context=context
            )
            if matches:
                match = matches[0].term
                entity.ns, entity.id, entity.term = match.db, match.id, match.entry_name
                yield entity
            else:
                annotations = gilda.annotate(
                    entity.term, namespaces=self.namespaces, context_text=context
                )
                for _, match, *_ in annotations:
                    match = match.term
                    annotated_entity = copy.deepcopy(entity)
                    annotated_entity.term = match.entry_name
                    annotated_entity.ns = match.db
                    annotated_entity.id = match.id
                    yield annotated_entity

    def __call__(
        self, entity: BioEntity, context: Optional[str] = None
    ) -> Iterator[BioEntity]:
        return self.ground(entity, context)


class ConditionGrounder(Grounder):
    def __init__(self):
        super().__init__(namespaces=CONDITION_NS)


class InterventionGrounder(Grounder):
    def __init__(self):
        super().__init__(namespaces=INTERVENTION_NS)
