from ..base.config import Config


class WhoConfig(Config):
    def __init__(self):
        super().__init__(registry="who")
