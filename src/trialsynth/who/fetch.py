import csv
import logging

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from ..base.config import Config
from ..base.fetch import Fetcher
from ..base.models import BioEntity, DesignInfo, Outcome, SecondaryId, Trial
from ..base.util import NAMESPACES, make_list, make_str

logger = logging.getLogger(__name__)


class WhoFetcher(Fetcher):
    def __init__(self, config: Config):
        super().__init__(config)

    def get_api_data(self, reload: bool = False):
        """Fetches data from the WHO ICTRP CSV file and transforms it into a list of :class:`Trial` objects

        Parameters
        ----------
        reload : bool
            Whether to reload the data from the API

        Returns
        -------
        None
        """
        trial_path = self.config.raw_data_path
        if trial_path.is_file() and not reload:
            self.load_saved_data()
            return
        path = self.config.get_data_path("ICTRP.csv")
        with open(path, "r") as file:
            trials = [trial for trial in file]

            for trial in tqdm(
                csv.reader(trials),
                desc="Reading CSV WHO data",
                total=len(trials),
                unit="trials",
            ):
                with logging_redirect_tqdm():
                    trial_id = trial[0].strip()
                    trial_id = trial_id.replace("\ufeff", "")
                    prefix = None
                    for p, pfix in NAMESPACES.items():
                        if trial_id.startswith(p) or trial_id.startswith(p.lower()):
                            prefix = pfix
                            break
                    else:
                        msg = f"could not identify {trial_id}"
                        raise ValueError(msg)

                    if trial_id.startswith("EUCTR"):
                        trial_id = trial_id.removeprefix("EUCTR")
                        trial_id = "-".join(trial_id.split("-")[:3])

                        # handling inconsistencies with ChiCTR trial IDs
                    if trial_id.lower().startswith("chictr-"):
                        trial_id = (
                            "ChiCTR-" + trial_id.lower().removeprefix("chictr-").upper()
                        )

                    trial_id = (
                        trial_id.removeprefix("JPRN-")
                        .removeprefix("CTIS")
                        .removeprefix("PER-")
                    )

                    who_trial = Trial(prefix, trial_id)

                    who_trial.title = make_str(trial[3])
                    who_trial.labels.append(make_str(trial[18]))

                    design_list = [
                        design.strip() for design in make_list(trial[19], ".")
                    ]
                    design_dict = {}

                    try:
                        for design_attr in design_list:
                            key, value = design_attr.split(":", 1)
                            design_dict[key.strip().lower()] = value.strip()
                        who_trial.design = DesignInfo(
                            allocation=design_dict.get("allocation"),
                            assignment=design_dict.get("intervention model"),
                            masking=design_dict.get("masking"),
                            purpose=design_dict.get("primary purpose"),
                        )
                    except Exception:
                        logger.debug(
                            f"Error in design attribute for curie: {who_trial.curie} using fallback"
                        )
                        pass

                    if who_trial.design is None:
                        who_trial.design = DesignInfo(fallback=make_str(trial[19]))

                    who_trial.conditions = [
                        BioEntity(
                            term=condition,
                            origin=who_trial.curie,
                            labels=["condition"],
                            source=self.config.registry,
                        )
                        for condition in make_list(trial[29], ";")
                    ]
                    who_trial.interventions = [
                        BioEntity(
                            term=intervention,
                            origin=who_trial.curie,
                            labels=["intervention"],
                            source=self.config.registry,
                        )
                        for intervention in make_list(trial[30], ";")
                        if intervention != "NULL"
                    ]
                    who_trial.primary_outcomes = [Outcome(measure=make_str(trial[36]))]
                    who_trial.secondary_outcomes = [
                        Outcome(measure=make_str(trial[37]))
                    ]
                    who_trial.secondary_ids = [
                        SecondaryId(id=id) for id in make_list(trial[2], ";")
                    ]
                    who_trial.source = self.config.registry
                    self.raw_data.append(who_trial)
        self.save_raw_data()
