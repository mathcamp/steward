"""
.. module:: server
   :synopsis: Steward server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Steward server

"""
import logging
import traceback
import types
import inspect
import zmq
import zmq.eventloop
from collections import defaultdict
from multiprocessing.pool import ThreadPool
from tornado import ioloop, gen
from . import streams
from . import tasks

zmq.eventloop.ioloop.install()

LOG = logging.getLogger(__name__)

class Server(object):
    """
    The server that handles tasks, events, and running commands from clients

    Parameters
    ----------
    conf : dict
        The configuration dictionary

    Attributes
    ----------
    running : bool
        True while the server is running
    conf : dict
        The configuration dictionary
    event_handlers : dict
        Mapping of event names to list of handlers
    tasklist : :py:class:`steward.tasks.TaskList`
        The tasklist loaded by the server
    pool : :py:class:`multiprocessing.pool.ThreadPool`
        A threadpool for running ``@threaded`` extensions

    """
    def __init__(self, conf):
        self.running = True
        self.conf = conf
        self.event_handlers = defaultdict(list)
        self.tasklist = tasks.TaskList()
        self.pool = ThreadPool(processes=conf['worker_threads'])

        # This socket accepts commands from multiple clients at a time
        streams.default_stream(conf['stream'], conf['server_socket'],
            zmq.ROUTER, True, self.client_callback)

        # This socket publishes events to clients
        self._pubstream = streams.default_stream(conf['stream'],
            conf['server_channel_socket'], zmq.PUB, True, lambda *args:None)

        self.apply_extensions(conf['extension_mods'])
        ioloop.IOLoop.instance().add_callback(self.tasklist.start)

    @gen.engine
    def client_callback(self, stream, uid, msg):
        """
        The method called when a client sends the server a message

        Parameters
        ----------
        stream : :py:class:`~steward.streams.BaseStream`
            The stream that received the message
        uid : str
            The uid of the client that sent the message
        msg : dict
            The message sent by the client

        """
        LOG.info("Got client command: %s" % msg)
        command = msg.get('cmd')

        # If the command exists on the Server object, run that
        try:
            attr_list = command.split('.')
            method = self
            for attr in attr_list:
                method = getattr(method, attr)
            
            if getattr(method, '__public__'):
                value = yield gen.Task(method, *msg.get('args', []),
                    **msg.get('kwargs', {}))
                if isinstance(value, Exception):
                    # If the sys.exc_info is stored on the exception, raise
                    # that to preserve the traceback
                    if hasattr(value, 'exc'):
                        raise value.exc[1], None, value.exc[2]
                    else:
                        raise value
                retval = {'val':value}
            else:
                raise AttributeError('{} is not public!'.format(command))
        except Exception as e:
            LOG.exception(e)
            retval = {'exc':traceback.format_exc()}
        finally:
            stream.send(uid, retval)

    def publish(self, name, data=None):
        """
        Publish an event

        Parameters
        ----------
        name : str
            Name of the event to publish
        data : object, optional
            The payload to send with the event (default None)

        """
        LOG.info("Publishing event %s", name)
        for handler in self.event_handlers.get(name, []):
            if handler(self, data) is True:
                LOG.info("Sending event %s has been blocked by "
                    "event handler %s", name, handler.__name__)
                return
        self._pubstream.send(name, data)

    def run(self):
        """Start the ioloop that runs the server"""
        io_loop = ioloop.IOLoop.instance()
        try:
            self.tasklist.start()
            LOG.info("Starting server")
            io_loop.start()
            return 0
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            io_loop.stop()
            LOG.info("Server stopped")
        return 1

    def stop(self):
        """Stop the server"""
        self.pool.close()

    def apply_extensions(self, mods):
        """
        Apply extensions modules

        Parameters
        ----------
        self : object
            The instance to apply the extensions to
        mods : list
            List of modules to load the extensions from

        """
        init_methods = []
        for mod in mods:
            members = inspect.getmembers(mod, callable)
            for name, member in members:
                if name.startswith('_'):
                    continue

                # If there is a method named 'init', add it to a list and run
                # them all together after loading all extensions
                if name == 'init':
                    init_methods.append(member)
                    continue

                # If this is a task, add it to the tasklist
                if isinstance(member, tasks.Task):
                    bound_task = types.MethodType(member, self, type(self))
                    self.tasklist.add(bound_task)
                # If this is an event handler, add it to the event_handlers
                elif hasattr(member, '__sub_event__'):
                    self.event_handlers[member.__sub_event__].append(member)
                elif hasattr(member, '__public__'):
                    name = name.lower()
                    if hasattr(self, name):
                        raise Exception("Server already has extension {}"
                        .format(name))

                    if inspect.isclass(member):
                        instance = member(self)
                        instance.__server__ = self
                        setattr(self, name, instance)
                        continue

                    argspec = inspect.getargspec(member)
                    if 'callback' not in argspec.args and not argspec.keywords:
                        raise Exception("server extension [{}] should take a "
                            "'callback' keyword!".format(name))

                    bound_method = types.MethodType(member, self, Server)
                    setattr(self, name, bound_method)

        for init_method in init_methods:
            # Only run the init methods after all modules are loaded
            init_method(self)

        # Order the event handlers by priority
        for handlers in self.event_handlers.itervalues():
            handlers.sort(key=lambda x:x.__priority__)
