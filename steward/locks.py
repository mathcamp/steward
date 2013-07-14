""" Tools for synchronizing requests and blocks """
import inspect
import os
from multiprocessing import RLock
from pyramid.path import DottedNameResolver
import contextlib
import functools
from collections import defaultdict

def lock(key, *l_args, **l_kwargs):
    """ Decorator for synchronizing a request """
    def wrapper(fxn):
        """ Wrapper for the synchronized request handler """
        @functools.wraps(fxn)
        def wrapped(*args):
            """ Acquire lock and do request """
            if len(args) == 1:
                request = args[0]
            elif len(args) == 2:
                request = args[1]
            else:
                raise TypeError("Locked method %s has more than 3 args!" %
                                fxn.__name__)
            argspec = inspect.getargspec(fxn)
            with request.registry.lock_factory(key, *l_args, **l_kwargs):
                if len(argspec.args) == 1:
                    return fxn(request)
                else:
                    return fxn(*args)
        return wrapped
    return wrapper


def request_lock(request, key, *args, **kwargs):
    """ Request method that accesses locks from a request """
    return request.registry.lock_factory(key, *args, **kwargs)


@contextlib.contextmanager
def noop():
    """ A no-op lock """
    yield


@contextlib.contextmanager
def file_lock(filename):
    """ Acquire a lock on a file using ``flock`` """
    import fcntl
    with open(filename, "w") as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX)
        yield


class ILockFactory(object):
    """
    Interface for generating locks

    Extend this class to use a different kind of lock for all of the
    synchronization in Steward.

    Parameters
    ----------
    config : :class:`pyramid.config.Configurator`
        The application's configurator

    """
    def __init__(self, config):
        self._config = config

    def __call__(self, key, expires=None, timeout=None):
        """
        Create a lock unique to the key

        Parameters
        ----------
        key : str
            Unique key to identify the lock to return
        expires : float, optional
            Maximum amount of time the lock may be held (default infinite)
        timeout : float, optional
            Maximum amount of time to wait to acquire the lock before rasing an
            exception (default infinite)

        Notes
        -----
        Not all ILockFactory implementations will respect the ``expires``
        and/or ``timeout`` options. Please refer to the implementation for
        details.

        """
        raise NotImplementedError


class DummyLockFactory(ILockFactory):
    """ No locking will occur """
    def __call__(self, key, *args, **kwargs):
        return noop()


class DefaultLockFactory(ILockFactory):
    """ Generate multiprocessing RLocks """
    def __init__(self, config):
        super(DefaultLockFactory, self).__init__(config)
        self._lock = RLock()
        self._locks = defaultdict(RLock)

    def __call__(self, key, *args, **kwargs):
        with self._lock:
            return self._locks[key]


class FileLockFactory(ILockFactory):
    """ Generate file-level locks that use ``flock`` """
    def __init__(self, config):
        super(FileLockFactory, self).__init__(config)
        settings = self._config.get_settings()
        self._lockdir = settings.get('steward.lock_dir',
                                     '/var/run/steward_locks/')
        os.makedirs(self._lockdir)

    def __call__(self, key, *args, **kwargs):
        return file_lock(os.path.join(self._lockdir, key))


def includeme(config):
    """ Configure the app """
    name_resolver = DottedNameResolver(__package__)
    settings = config.get_settings()
    factory_name = settings.get('steward.lock_factory')
    if factory_name is None:
        factory_name = 'steward.locks:DefaultLockFactory'
    elif factory_name == 'dummy':
        factory_name = 'steward.locks:DummyLockFactory'
    elif factory_name == 'file':
        factory_name = 'steward.locks:FileLockFactory'
    config.registry.lock_factory = name_resolver.resolve(factory_name)(config)
    config.add_request_method(request_lock, name='lock')
