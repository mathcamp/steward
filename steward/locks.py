""" Tools for synchronizing requests and blocks """
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
            with request.registry.lock_factory(key, *l_args, **l_kwargs):
                return fxn(*args)
        return wrapped
    return wrapper

def request_lock(request, key, *args, **kwargs):
    """ Request method that accesses locks from a request """
    return request.registry.lock_factory(key, *args, **kwargs)

class ILockFactory(object):
    """
    Interface for generating locks

    Extend this class to use a different kind of lock for all of the
    synchronization in Steward.

    """
    def __call__(self, key, *args, **kwargs):
        """
        Create a lock unique to the key

        Parameters
        ----------
        key : str
            Unique key to identify the lock to return
        args : list
            Positional arguments for custom implementations
        kwargs : dict
            Keyword arguments for custom implementations

        Notes
        -----
        The keyword arguments exist to allow certain lock factory
        implementations to be customized with behaviors like timeouts.

        """
        raise NotImplementedError

@contextlib.contextmanager
def noop():
    """ A no-op lock """
    yield

class DummyLockFactory(ILockFactory):
    """ No locking will occur """
    def __call__(self, key, *args, **kwargs):
        return noop()

class DefaultLockFactory(ILockFactory):
    """ Generate multiprocessing RLocks """
    def __init__(self):
        self._locks = defaultdict(RLock)

    def __call__(self, key, *args, **kwargs):
        return self._locks[key]

def includeme(config):
    """ Configure the app """
    name_resolver = DottedNameResolver(__package__)
    settings = config.get_settings()
    config.registry.lock_factory = name_resolver.resolve(
        settings.get('steward.lock_factory',
                     'steward.locks:DefaultLockFactory'))()
    config.add_request_method(request_lock, name='lock')
