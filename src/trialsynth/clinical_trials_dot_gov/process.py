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
        """Initialize the ClinicalTrials.gov processor.

        Parameters
        ----------
        reload_api_data :
            If True, the API data will be reloaded from the ClinicalTrials.gov REST API.
        store_samples :
            If True, the processor will store sample data for validation.
        validate :
            If True, the processor will validate the data.
        condition_grounder :
            A grounder to use for grounding conditions. Defaults to CTConditionGrounder().
        intervention_grounder :
            A grounder to use for grounding interventions. Defaults to CTInterventionGrounder().
        """
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
