import copy
import logging
import warnings
from typing import Iterator, Optional, Callable, Literal

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

import spacy

logger = logging.getLogger(__name__)


GrounderSignature = Callable[
    [str, Optional[str], Optional[list[str]], Optional[list[str]]],
    list[ScoredMatch]
]
AnnotatorSignature = Optional[Callable[[str, Optional[str]], list[Annotation]]]


class Annotator:
    def __init__(
        self,
        *,
        namespaces: Optional[list[str]] = None,
        mesh_prefix: Optional[Literal["mesh", "MESH"]] = "MESH"
    ):
        """Base class for annotators that annotate text with named entities.

        Parameters
        ----------
        namespaces : Optional[list[str]]
            A list of namespaces to consider for annotation. If None, defaults to ["MESH"].
        mesh_prefix : Optional[Literal["mesh", "MESH"]]
            The prefix to use for MESH grounding. If None, defaults to "MESH". Use
            this to specify the capitalization of the MESH prefix for grounding.
        """
        if namespaces is None:
            namespaces = [mesh_prefix]
        self.namespaces = namespaces

    def __call__(self, text: str, *, context: str = None) -> list[Annotation]:
        return self.annotate(text, context=context)

    @must_override
    def annotate(self, text: str, *, context: str = None) -> list[Annotation]:
        pass


class GildaAnnotator(Annotator):
    def __init__(
        self,
        *,
        namespaces: Optional[list[str]] = None,
        mesh_prefix: Optional[Literal["mesh", "MESH"]] = "MESH"
    ):
        if namespaces is None:
            logger.info("No namespaces provided, using default Gilda namespaces.")
            namespaces = gilda.grounder.DEFAULT_NAMESPACE_PRIORITY
        super().__init__(namespaces=namespaces, mesh_prefix=mesh_prefix)
    def annotate(self, text: str, *, context: str = None):
        return gilda.annotate(
            text=text, context_text=context, namespaces=self.namespaces
        )


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
    restrict_mesh_prefix : list[str], optional
        A list of MESH tree prefixes to restrict grounding to (default: None).
    annotator : Callable[[str, Optional[str]], list[Tuple[Annotation]]], optional
        A callable that takes a string and returns a list of annotations
        (default: GildaAnnotator).
    grounder_func : Optional[GrounderSignature], optional
        A callable that takes a string and returns a list of ScoredMatches.
        If None, defaults to `gilda.ground` (default: None).
    mesh_prefix : Optional[Literal["mesh", "MESH"]]
        The prefix to use for MESH grounding. If None, defaults to "MESH". Use
        this to specify the capitalization of the MESH prefix for grounding.

    Attributes
    ----------
    namespaces : Optional[list[str]]
        A list of namespaces to consider for grounding.
    restrict_mesh_prefix : list[str]
        A list of MESH tree prefixes to restrict grounding to.
    annotator : Callable[[str, Optional[str]], list[Annotation]]
        A callable that annotates text with named entities.
    grounder_func : GrounderSignature
        A callable that grounds text to named entities.
    mesh_prefix : Optional[Literal["mesh", "MESH"]]
        The prefix to use for MESH grounding. Should match the capitalization
        returned by the grounding function.
    """

    def __init__(
        self,
        *,
        namespaces: Optional[list[str]] = None,
        restrict_mesh_prefix: list[str] = None,
        annotator: AnnotatorSignature = GildaAnnotator(),
        grounder_func: Optional[GrounderSignature] = None,
        mesh_prefix: Optional[Literal["mesh", "MESH"]] = "MESH"
    ):
        self.namespaces: Optional[list[str]] = namespaces
        self.restrict_mesh_prefix = restrict_mesh_prefix
        self.annotator = annotator
        if grounder_func is None:
            grounder_func = gilda.ground
        self.grounder_func = grounder_func
        self.mesh_prefix = mesh_prefix

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
        self, entity: BioEntity, *, db_ns, db_id: str, norm_text: str
    ) -> BioEntity:
        grounded_entity = copy.deepcopy(entity)
        grounded_entity.ns = db_ns
        grounded_entity.ns_id = db_id
        grounded_entity.grounded_term = norm_text
        return grounded_entity

    def _yield_entity(
        self, entity: BioEntity, match: ScoredMatch
    ) -> Iterator[BioEntity]:
        groundings_dict = dict(match.get_groundings())
        mesh_id = groundings_dict.get(self.mesh_prefix)

        if mesh_id:
            if self.restrict_mesh_prefix and any(mesh_client.has_tree_prefix(mesh_id, prefix) for prefix in self.restrict_mesh_prefix):
                yield self._create_grounded_entity(
                    entity, db_ns=self.mesh_prefix, db_id=mesh_id, norm_text=match.term.entry_name
                )
            if not self.restrict_mesh_prefix:
                yield self._create_grounded_entity(
                    entity, db_ns=self.mesh_prefix, db_id=mesh_id, norm_text=match.term.entry_name
                )
        else:
            # If no MESH ID is found, we yield the original entity with the match
            yield self._create_grounded_entity(
                entity,
                db_ns=match.term.db,
                db_id=match.term.id,
                norm_text=match.term.entry_name,
            )

    def ground(
        self,
        entity: BioEntity,
        context: Optional[str] = None
    ) -> Iterator[BioEntity]:
        """Ground a BioEntity to a CURIE."""
        entity = self.preprocess(entity)
        # Do special handling for MESH entities
        if entity.ns and entity.ns == self.mesh_prefix and entity.ns_id:
            mesh_name = mesh_client.get_mesh_name(entity.ns_id, offline=True)
            if mesh_name:
                entity.grounded_term = mesh_name
                yield entity
            else:
                matches = self.grounder_func(entity.text, namespaces=[self.mesh_prefix])
                if matches:
                    yield from self._yield_entity(entity, matches[0])
        # If the entity already has a namespace and ID, we assume it's already grounded
        elif entity.ns and entity.ns_id:
            yield entity
        # Otherwise, we ground the entity using Gilda
        else:
            matches = self.grounder_func(
                entity.text, namespaces=self.namespaces, context=context
            )
            if matches:
                yield from self._yield_entity(entity, matches[0])
            else:
                annotations = self.annotator(entity.text, context=context)
                for annotation in annotations:
                    yield from self._yield_entity(entity, annotation.matches[0])
                # If no matches are found, we try to annotate the description if it exists
                if entity.description:
                    annotations = self.annotator(
                        entity.description, context=context
                    )
                    for annotation in annotations:
                        yield from self._yield_entity(entity, annotation.matches[0])


class ConditionGrounder(Grounder):
    def __init__(
        self,
        namespaces: Optional[list[str]] = None,
        annotator: Optional[AnnotatorSignature] = None,
        grounder_func: Optional[GrounderSignature] = None,
        mesh_prefix: Optional[Literal["mesh", "MESH"]] = "MESH"
    ):
        if namespaces is None:
            namespaces = CONDITION_NS
        if annotator is None:
            annotator = GildaAnnotator(namespaces=namespaces)
        super().__init__(
            namespaces=namespaces,
            restrict_mesh_prefix=['C', 'F'],
            annotator=annotator,
            grounder_func=grounder_func,
            mesh_prefix=mesh_prefix
        )


class InterventionGrounder(Grounder):
    def __init__(
        self,
        namespaces: Optional[list[str]] = None,
        annotator: Optional[AnnotatorSignature] = None,
        grounder_func: Optional[GrounderSignature] = None,
        mesh_prefix: Literal["MESH", "mesh"] = "MESH"
    ):
        if namespaces is None:
            namespaces = INTERVENTION_NS
        if annotator is None:
            annotator = GildaAnnotator(namespaces=namespaces)
        super().__init__(
            namespaces=namespaces,
            restrict_mesh_prefix=['D', 'E'],
            annotator=annotator,
            grounder_func=grounder_func,
            mesh_prefix=mesh_prefix
        )
