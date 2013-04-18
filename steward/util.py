"""
.. module:: util
   :synopsis: Utility methods

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Utility methods

"""
import functools
import threading
import logging

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
        The name of the event to handle (regex-friendly)
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

    Event handlers work with regular expressions as well::

        @event_handler('order/.*')
        def handle_all_orders(self, order):
            logging.info("Someone ordered a %s!", order)

    Any capture groups defined in the regular expression will be passed in as arguments::

        @event_handler('order/(.*)')
        def handle_all_orders(self, order, meal):
            logging.info("Someone ordered a %s for %s!", order, meal)

    """
    def decorator(fxn):
        """The actual decorator for event handlers"""
        fxn.__sub_event__ = name
        fxn.__priority__ = priority
        return fxn
    return decorator

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
        def deploy(self):
            return _do_deploy()

    Alternatively, you may make the serialized function return False
    immediately if it is already running, rather than queueing it for later::

        @public
        @serialize(blocking=False)
        def deploy(self):
            return _do_deploy()

    """
    def create_wrapper(blocking, fxn):
        """Create the wrapper for the serialized function"""
        fxn.__lock__ = threading.RLock()
        @functools.wraps(fxn)
        def wrapper(*args, **kwargs):
            """Wrapper for the serialized function"""
            if not fxn.__lock__.acquire(blocking=blocking):
                return False
            try:
                result = fxn(*args, **kwargs)
            finally:
                fxn.__lock__.release()
            return result
        return wrapper

    if args:
        return create_wrapper(True, args[0])
    elif kwargs:
        return functools.partial(create_wrapper, kwargs.pop('blocking'))
    else:
        raise TypeError("@serialize called with wrong args!")

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
