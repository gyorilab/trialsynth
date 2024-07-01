from .util import PATTERNS


def is_valid(pattern: str, trial_id: str) -> bool:
    """Validates a trial ID against a pattern

    Parameters
    ----------
    pattern : str
        The pattern to validate against
    trial_id : str
        The trial ID to validate

    Returns
    -------
    bool
        Whether the trial ID is valid
    """
    if pattern in PATTERNS and not PATTERNS[pattern].match(trial_id):
        return False
    return True
