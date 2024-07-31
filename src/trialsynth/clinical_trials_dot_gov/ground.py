from overrides import overrides

from ..base.ground import ConditionGrounder, InterventionGrounder
from ..base.models import BioEntity


class CTConditionGrounder(ConditionGrounder):
    @overrides
    def preprocess(self, entity: BioEntity, *kwargs) -> BioEntity:
        return entity


class CTInterventionGrounder(InterventionGrounder):
    @overrides
    def preprocess(self, entity: BioEntity, *kwargs) -> BioEntity:
        return entity
