""" Utilities for parsing settings """

def asdict(config, value_type=lambda x:x):
    """ Parses config values from .ini file and returns a dictionary """
    result = {}
    if config is None:
        return result
    for line in [line.strip() for line in config.splitlines()]:
        if not line:
            continue
        key, value = line.split('=', 1)
        result[key.strip()] = value_type(value.strip())
    return result

