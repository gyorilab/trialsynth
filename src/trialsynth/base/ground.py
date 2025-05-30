import copy
import logging
import warnings
from collections import defaultdict
from typing import Iterator, Optional, Callable, Tuple 

nmslib_logger = logging.getLogger('nmslib')
nmslib_logger.setLevel(logging.ERROR)
warnings.simplefilter('ignore')

import gilda
from gilda.grounder import Annotation, ScoredMatch
from indra.databases import mesh_client

from .models import BioEntity
from .util import (
    CONDITION_NS,
    INTERVENTION_NS,
    must_override
)

import scispacy
import spacy
from scispacy.abbreviation import AbbreviationDetector
from scispacy.linking import EntityLinker

logger = logging.getLogger(__name__)


class Annotator:
    def __init__(
        self,
        *,
        namespaces: Optional[list[str]] = None,
    ):
        """Base class for annotators that annotate text with named entities.

        Parameters
        ----------
        namespaces : Optional[list[str]]
            A list of namespaces to consider for annotation. If None, defaults to ["MESH"].
        """
        if namespaces is None:
            namespaces = ["MESH"]
        self.namespaces = namespaces

    def __call__(self, text: str, *, context: str = None) -> list[Annotation]:
        return self.annotate(text, context=context)

    @must_override
    def annotate(self, text: str, *, context: str = None) -> list[Annotation]:
        pass

class GildaAnnotator(Annotator):
    def annotate(self, text: str, *, context: str = None):
        return gilda.annotate(text=text, context_text=context, namespaces=self.namespaces)

class SciSpacyAnnotator(Annotator):
    def __init__(self, *, model: str, namespaces: Optional[list[str]] = None):
        super().__init__(namespaces=namespaces)
        try:
            self.model = spacy.load(model)
        except OSError:
            logger.info("spaCy model not found")
            raise

    def annotate(self, text: str, *, context: str = None):
        context_text = context if context is not None else text
        doc = self.model(text)

        annotations: list[Annotation] = []
        for entity in doc.ents:
            matches = gilda.ground(entity.text, namespaces=self.namespaces, context=context_text)
            if matches:
                annotations.append(
                    Annotation(entity.text, matches, entity.start_char, entity.end_char)
                )
            return annotations

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

    def __init__(
        self,
        *,
        namespaces: Optional[list[str]] = None,
        restrict_mesh_prefix: list[str] = None,
        annotator: Callable[[str], list[Tuple[Annotation]]] = Annotator(),
    ):
        self.namespaces: Optional[list[str]] = namespaces
        self.restrict_mesh_prefix = restrict_mesh_prefix
        self.annotator = annotator

    @must_override
    def preprocess(self, entity: BioEntity) -> BioEntity:
        """Preprocess the BioEntity before grounding.

        This method can be overridden by subclasses to perform any necessary preprocessing
        steps on the BioEntity before grounding it.

        Parameters
        ----------
        entity : BioEntity
            The BioEntity to preprocess.

        Returns
        -------
        BioEntity
            The preprocessed BioEntity.
        """

    def __call__(
        self, entity: BioEntity, context: Optional[str] = None
    ) -> Iterator[BioEntity]:
        return self.ground(entity, context)
    
    def _create_grounded_entity(
        self, entity: BioEntity, *, mesh_id: str, norm_text: str
    ) -> BioEntity:
        grounded_entity = copy.deepcopy(entity)
        grounded_entity.ns = 'MESH'
        grounded_entity.ns_id = mesh_id
        grounded_entity.grounded_term = norm_text
        return grounded_entity

    def _yield_entity(
        self, entity: BioEntity, match: ScoredMatch
    ) -> Iterator[BioEntity]:
        groundings_dict = dict(match.get_groundings())
        mesh_id = groundings_dict.get('MESH')
        
        if mesh_id:
            if self.restrict_mesh_prefix and any(mesh_client.has_tree_prefix(mesh_id, prefix) for prefix in self.restrict_mesh_prefix):
                yield self._create_grounded_entity(
                    entity, mesh_id=mesh_id, norm_text=match.term.entry_name
                )
            if not self.restrict_mesh_prefix:
                yield self._create_grounded_entity(
                    entity, mesh_id=mesh_id, norm_text=match.term.entry_name
                )

    def ground(
        self, entity: BioEntity, context: Optional[str] = None
    ) -> Iterator[BioEntity]:
        """Ground a BioEntity to a CURIE."""
        entity = self.preprocess(entity)
        if entity.ns and entity.ns.upper() == "MESH" and entity.ns_id:
            mesh_name = mesh_client.get_mesh_name(entity.ns_id, offline=True)
            if mesh_name:
                entity.grounded_term = mesh_name
                yield entity
            else:
                matches = gilda.ground(entity.text, namespaces=["MESH"])
                if matches:
                    yield from self._yield_entity(entity, matches[0])
        else:
            matches = gilda.ground(
                entity.text, namespaces=self.namespaces, context=context
            )
            if matches:
                yield from self._yield_entity(entity, matches[0])
            else:
                annotations = self.annotator(entity.text)
                for annotation in annotations:
                    yield from self._yield_entity(entity, annotation.matches[0])


class ConditionGrounder(Grounder):
    def __init__(
        self,
        namespaces: Optional[list[str]] = None,
        annotator: Callable[[str], list[Tuple[Annotation]]] = None
    ):
        if namespaces is None:
            namespaces = CONDITION_NS
        if annotator is None:
            annotator = GildaAnnotator(namespaces=namespaces)
        super().__init__(
            namespaces=namespaces,
            restrict_mesh_prefix=['C', 'F'],
            annotator=annotator
        )


class InterventionGrounder(Grounder):
    def __init__(
        self,
        namespaces: Optional[list[str]] = None,
        annotator: Callable[[str], list[Tuple[Annotation]]] = None
    ):
        if namespaces is None:
            namespaces = INTERVENTION_NS
        if annotator is None:
            annotator = GildaAnnotator(namespaces=namespaces)
        super().__init__(
            namespaces=namespaces,
            restrict_mesh_prefix=['D', 'E'],
            annotator=annotator
        )
