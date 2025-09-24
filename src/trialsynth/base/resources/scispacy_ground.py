import logging
import gilda
from typing import Optional
from trialsynth.base.ground import Annotator, Annotation

try:
    import spacy
except ImportError:
    raise ImportError("Please install scispacy to use the SciSpacyAnnotator.")


logger = logging.getLogger(__name__)


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
