from ..base.process import Processor
from ..base.ground import Grounder
from .config import CTConfig
from .fetch import CTFetcher
from .ground import CTConditionGrounder, CTInterventionGrounder
from .transform import CTTransformer
from .validate import CTValidator


class CTProcessor(Processor):
    def __init__(
        self,
        reload_api_data: bool,
        store_samples: bool,
        validate: bool,
        condition_grounder: Grounder = CTConditionGrounder(),
        intervention_grounder: Grounder = CTInterventionGrounder(),
    ):
        super().__init__(
            config=CTConfig(),
            fetcher=CTFetcher(CTConfig()),
            transformer=CTTransformer(),
            validator=CTValidator(),
            condition_grounder=condition_grounder,
            intervention_grounder=intervention_grounder,
            reload_api_data=reload_api_data,
            store_samples=store_samples,
            validate=validate,
        )
