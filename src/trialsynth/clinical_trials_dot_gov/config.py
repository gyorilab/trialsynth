from ..base.config import Config


class CTConfig(Config):
    def __init__(self):
        super().__init__(registry="clinicaltrials")
