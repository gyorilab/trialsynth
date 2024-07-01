import os
import sys
import shutil
import logging
if sys.version_info[0] == 3:
    from configparser import RawConfigParser
else:
    from ConfigParser import RawConfigParser

logger = logging.getLogger(__name__)

class TrialSynthConfigError(Exception):
    pass

def create_config_dict(registry):
    """Load the configuration file into the config_file dictionary
    """
    home_dir = os.path.expanduser('~')
    config_dir = os.path.join(home_dir, '.config', registry)
    config_path = os.path.join(config_dir, 'config.ini')
    default_config_path = os.path.join(os.path.dirname(__file__),
                                       'resources/default_config.ini')
    if not os.path.isfile(config_path):
        try:
            os.makedirs(config_dir)
        except Exception:
            logger.warning(config_dir + ' already exists')
        try:
            shutil.copyfile(default_config_path, config_path)
        except Exception:
            logger.warning('Could not copy default config file.')

    try:
        config_dict = {}
        parser = RawConfigParser()
        parser.optionxform = lambda x: x
        parser.read(config_path)
        sections = parser.sections()

        options = parser.options('trialsynth')
        for option in options:
            config_dict[option] = str(parser.get('trialsynth', option))

        if registry in sections:
            options = parser.options(registry)
            for option in options:
                if option in config_dict:
                    logger.info("Overwriting package level configuration with registry level for option: " + option)
                config_dict[option] = str(parser.get(registry, option))
        else:
            raise ValueError(f"Registry [{registry}] not found in configuration file.")

    except Exception as e:
        logger.warning("Could not load configuration file due to exception. "
                       "Only environment variable equivalents will be used.")
        return None

    for key in config_dict.keys():
        if config_dict == '':
            config_dict[key] = None
        elif isinstance(config_dict[key], str):
            config_dict[key] = os.path.expanduser(config_dict[key])
        return config_dict

def get_config(key: str, config_dict: dict, failure_ok: bool=False):
    """
    Get a configuration value from the environment or config file.
    Parameters
    ----------
    key : str
        The key for the configuration value
    config_dict : dict
        The configuration dictionary
    failure_ok : bool
        If False and the configuration is missing, an WhoConfigError is
            raised. If True, None is returned and no error is raised in case
            of a missing configuration. Default: False

    Returns
    -------
    value : str or None
        The configuration value or None if the configuration value doesn't
        exist and failure_ok is set to True.
    """


    err_msg = "Key %s not in environment or config file." % key
    if key in os.environ:
        return os.environ[key]
    elif key in config_dict:
        val = config_dict[key]
        # We interpret an empty value in the config file as a failure
        if val is None and not failure_ok:
            msg = 'Key %s is set to an empty value in config file.' % key
            raise TrialSynthConfigError(msg)
        else:
            return val
    elif not failure_ok:
        raise TrialSynthConfigError(err_msg)
    else:
        return None
