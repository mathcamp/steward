"""
.. module:: config
   :synopsis: Loads configuration values

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Loads configuration values

Look at the etc/steward.yaml for a description of all the fields

"""
import os.path
import importlib
import yaml
import pkgutil
import argparse
import sys
import logging
import logging.config
from collections import OrderedDict

LEVEL_MAP = OrderedDict([
    ('debug', logging.DEBUG),
    ('info', logging.INFO),
    ('warning', logging.WARNING),
    ('error', logging.ERROR),
])
CONF_FILE = '/etc/steward.yaml'
COMMON_DEFAULTS = {
    'server_socket': 'tcp://127.0.0.1:1403',
    'server_channel_socket': 'tcp://127.0.0.1:1404',
    'stream': 'JsonStream',
    'log_level': 'warning',
    'log_dir': None,
}
SERVER_DEFAULTS = {
    'extensions': [],
    'pkg_extensions': [],
    'worker_threads': 10,
}
CLIENT_DEFAULTS = {
    'server': None,
    'client_extensions': [],
    'client_pkg_extensions': [],
    'prompt': '8==D ',
    'aliases': {},
    'meta': {},
}
BASE_PKG_EXTENSIONS = ['steward.extensions']

def get_log_config(conf):
    """Get the dictionary configuration for logging"""
    if conf['log_dir'] and not os.path.exists(conf['log_dir']):
        os.makedirs(conf['log_dir'])
    log_config = {
        'version' : 1,
        'disable_existing_loggers': True,
        'formatters': {
            'simple': {
                'format': '%(levelname)s %(asctime)s %(message)s'
            },
        },
        'root': {
            'handlers': ['console', 'filelog'] if conf['log_dir'] \
                else ['console'],
            'level':LEVEL_MAP[conf['log_level'].lower()],
        },
        'loggers': {
            'steward': {
                'level': LEVEL_MAP[conf['log_level'].lower()],
                'handlers': ['console', 'filelog'] if conf['log_dir'] \
                    else ['console'],
                'propagate': False,
            },
        },
        'handlers': {
            'console':{
                'level': LEVEL_MAP[conf['log_level'].lower()],
                'class':'logging.StreamHandler',
                'formatter': 'simple',
            },
        }
    }

    if conf['log_dir']:
        log_config['handlers']['filelog'] = {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'simple',
            'filename': os.path.join(conf['log_dir'], 'steward.log'),
            'maxBytes': 1024*1024*2,
            'backupCount': 5,
        }


    return log_config

def bare_config(conf_file):
    """Load a config file, preserving default values"""
    config = {}
    config.update(COMMON_DEFAULTS)
    config.update(SERVER_DEFAULTS)
    config.update(CLIENT_DEFAULTS)
    if conf_file is not None:
        if os.path.exists(conf_file):
            file_config = yaml.load(open(conf_file, 'r'))
            config.update(file_config)

    return config

def load_config(is_server, conf_file=CONF_FILE):
    """
    Load the configuration options from a file.
    
    Parameters
    ----------
    conf_file : str, optional
        The file to load from.

    """
    config = bare_config(conf_file)
    config['extension_mods'] = load_extensions(config, is_server)
    return config

__loaded_modules__ = set()

def _load_extensions(dirs):
    """
    Dynamically load modules from a list of directories

    Parameters
    ----------
    dirs : list
        List of paths to load modules from

    Raises
    ------
    ImportError
        If there are duplicate modules

    """
    modules = []
    for loader, name, is_pkg in pkgutil.walk_packages(dirs):
        if name in __loaded_modules__:
            raise ImportError("Module {0} is already loaded! "
            "Are there two modules named {0}?".format(name))
        loaded_mod = loader.find_module(name).load_module(name)
        if not is_pkg:
            modules.append(loaded_mod)
            __loaded_modules__.add(name)
    return modules

def _load_pkg_extensions(packages):
    """
    Dynamically load extension modules from a package

    Parameters
    ----------
    packages : list
        List of packages to load modules from

    Raises
    ------
    ImportError
        If there are duplicate modules or if package doesn't exist

    """
    paths = []
    for pkg in packages:
        package = importlib.import_module(pkg)
        paths.append(os.path.dirname(package.__file__))
    return _load_extensions(paths)

def load_extensions(config, is_server):
    """
    Take a config dict and load the specified extensions

    Parameters
    ----------
    config : dict
    is_server : bool

    """
    if is_server:
        ext = _load_extensions(config['extensions'])
        ext += _load_pkg_extensions(BASE_PKG_EXTENSIONS +
            config['pkg_extensions'])
    else:
        ext = _load_extensions(config['client_extensions'])
        ext += _load_pkg_extensions(BASE_PKG_EXTENSIONS +
            config['client_pkg_extensions'])
    return ext

class CMDLineOptionsParserMixin(object):
    """Mixin for parsing configuration options from the command line"""
    def options(self, parser):
        """
        Add arguments to the options parser. Override this in
        subclasses to add custom command line options

        Parameters
        ----------
        parser : :py:class:`argparse.ArgumentParser`

        """

    def configure(self, args):
        """
        Configure the class based on the arguments parsed. Override this in
        subclasses to pull out the values passed in to the command line.

        Parameters
        ----------
        args : dict
            Dictionary of option-value pairs as parsed by :py:mod:`argparse`

        """

    def get_config(self, is_server, argv=None):
        """
        Parse options from the command line and any relevant config files

        Parameters
        ----------
        is_server : bool
            If true, will parse options for server configuration
        argv : list, optional
            List of arguments to parse. Defaults to sys.argv[1:]

        Returns
        -------
        config : dict
            Dictionary of config options

        """
        if argv is None:
            argv = sys.argv[1:]

        parser = argparse.ArgumentParser(
            description=self.__doc__.split('\n')[0])

        common_group = parser.add_argument_group()
        common_group.add_argument('-c', '--conf-file', default=CONF_FILE,
            help="Configuration file to read from (default %(default)s")
        common_group.add_argument('-l', '--log-level', choices=LEVEL_MAP.keys(),
            help="Log level")
        common_group.add_argument('--stream',
            help="Class for sending data over zmq")
        common_group.add_argument('--server-socket',
            help="Socket for the clients to connect to")
        common_group.add_argument('--server-channel-socket',
            help="Socket for the clients to connect to for event notifications")

        if is_server:
            server_group = parser.add_argument_group()
            server_group.add_argument('--extensions',
                type=lambda x:x.split(','),
                help="Directories to look for server extensions")
            server_group.add_argument('--pkg-extensions',
                type=lambda x:x.split(','),
                help="Python packages containing server extensions")
            server_group.add_argument('--worker-threads', type=int,
                help="Size of the thread pool for blocking calls")
            server_group.add_argument('--log-dir',
                help="Directory to write log files")
        else:
            client_group = parser.add_argument_group()
            client_group.add_argument('--server',
                help="Remote server to connect to via ssh")
            client_group.add_argument('--client-extensions',
                type=lambda x:x.split(','),
                help="Directories to look for client extensions")
            client_group.add_argument('--client-pkg-extensions',
                type=lambda x:x.split(','),
                help="Python packages containing client extensions")

        self.options(parser)
        args = vars(parser.parse_args(argv))

        config = bare_config(args['conf_file'])

        for default_dict in (COMMON_DEFAULTS,
        SERVER_DEFAULTS, CLIENT_DEFAULTS):
            for key in default_dict:
                val = args.get(key)
                if val is None:
                    continue
                config[key] = val

        if is_server:
            logging.config.dictConfig(get_log_config(config))
        else:
            logging.basicConfig(level=LEVEL_MAP[config['log_level'].lower()])

        self.configure(args)
        config['extension_mods'] = load_extensions(config, is_server)
        return config
