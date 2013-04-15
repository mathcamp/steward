"""
.. module:: util
   :synopsis: Utility methods

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Utility methods

"""
import functools
import sys
import logging
from datetime import timedelta
from tornado import gen, ioloop

LOG = logging.getLogger(__name__)

def public(fxn):
    """
    Decorator for methods on server that are callable from clients

    Notes
    -----
    ::

        @public
        def deploy(self):
            _deploy_my_code()
            return True

    """
    fxn.__public__ = True
    return fxn

def private(fxn):
    """
    Decorator for methods on server that are attached to the server but not
    callable from clients

    Notes
    -----
    This would be used for methods that you want to expose to other extensions,
    but do not want to expose to clients. For example::

        @private
        def persist(self, key, value):
            return _store_in_database(key, value)

    """
    fxn.__public__ = False
    return fxn

def invisible(fxn):
    """
    Decorator for methods callable from, but not visible to, clients.
    
    Notes
    -----
    Decorate a function with this to prevent it from cluttering up the function
    list::

        @invisible
        def test_debug(self):
            return "I'm a little teapot"

    """
    fxn.__invisible__ = True
    fxn.__public__ = True
    return fxn

def event_handler(name, priority=100):
    """
    Decorator for event handlers.

    Methods with this decorator will be called by the server before publishing
    an event to clients.

    Parameters
    ----------
    name : str
        The name of the event to handle
    priority : int, optional
        The priority order of execution of this handler (lower goes first)
        (default 100)

    Notes
    -----
    For events that pass in mutable data types (like dicts), you can modify
    them before they are sent out to clients. If the event handler returns
    True, the event will not be sent to further handlers or the clients.

    This handler will block 'server_start' events for staging servers::

        @event_handler('server_start', priority=1)
        def filter_staging_servers(self, payload):
            if payload['name'].startswith('staging'):
                return True

    This handler adds a side of spam to all the 'order' events::

        @event_handler('order')
        def add_side_of_spam(self, order):
            order['side'] = 'spam'

    If the event uses a static type for the payload, you can still write an
    event handler that mutates it by going through the
    :py:meth:`steward.server.Server.publish` method

    This handler converts all orders of eggs to an order of spam::
        
        @event_handler('order', priority=10)
        def you_want_spam(self, order):
            if order == 'eggs':
                self.publish('order', 'spam')
                return True

    """
    def decorator(fxn):
        """The actual decorator for event handlers"""
        fxn.__sub_event__ = name
        fxn.__priority__ = priority
        return fxn
    return decorator

def threaded(fxn):
    """
    Decorator for synchronous, blocking server methods.

    Since all server commands must be run asynchronously, this decorator
    provides an easy way to turn a typical blocking call into a call run in a
    background thread::
    
        @public
        @threaded
        def ls(self):
            return subprocess.check_output(['ls'])

    """
    @functools.wraps(fxn)
    def wrapper(self, *args, **kwargs):
        """Wrap the blocking command"""
        callback = kwargs.pop('callback')
        def run_blocking_cmd():
            """Run a blocking command in a thread"""
            try:
                retval = fxn(self, *args, **kwargs)
            except Exception as e:
                retval = e
                retval.exc = sys.exc_info()
            ioloop.IOLoop.instance().add_callback(lambda:callback(retval))
        # If we're inside a namespace, load the pool off the server
        if hasattr(self, 'pool'):
            pool = self.pool
        else:
            pool = self.__server__.pool
        pool.apply_async(run_blocking_cmd)
    return wrapper

def serialize(*args, **kwargs):
    """
    Decorator for server methods that should run one-at-a-time.

    If the method is currently being run, it will asynchronously sleep until
    that call is complete.

    Notes
    -----
    An example of forcing a single deploy at a time::

        @public
        @serialize
        @gen.engine
        def deploy(self, callback=None):
            result = yield gen.Task(_do_deploy)
            callback(result)

    Alternatively, you may make the serialized function return False
    immediately if it is already running, rather than queueing it for later::

        @public
        @serialize(blocking=False)
        @gen.engine
        def deploy(self, callback=None):
            result = yield gen.Task(_do_deploy)
            callback(result)

    """
    def create_wrapper(blocking, fxn):
        """Create the wrapper for the serialized function"""
        @functools.wraps(fxn)
        @gen.engine
        def wrapper(*args, **kwargs):
            """Wrapper for the serialized function"""
            callback = kwargs.pop('callback')
            while getattr(fxn, 'running', False):
                if not blocking:
                    callback(False)
                    return
                ioloop.IOLoop.instance().add_timeout(timedelta(seconds=0.1),
                    (yield gen.Callback('sleep')))
                yield gen.Wait('sleep')
            fxn.running = True
            result = yield gen.Task(fxn, *args, **kwargs)
            fxn.running = False
            callback(result)
        return wrapper

    if args:
        return create_wrapper(True, args[0])
    elif kwargs:
        return functools.partial(create_wrapper, kwargs.pop('blocking'))
    else:
        raise TypeError("@serialize called with wrong args!")

serialize.running = set()

def load_class(path, default=None):
    """
    Load a class dynamically from a path

    Parameters
    ----------
    path : str
        Path to the class to load
    default : str, optional
        If present, will search for the class in this module by default

    """
    try:
        last_dot = path.rindex('.')
        mod_name = path[:last_dot]
    except ValueError:
        last_dot = -1
        mod_name = default
    class_name = path[last_dot + 1:]
    mod = __import__(mod_name, fromlist=[class_name])
    return getattr(mod, class_name)
