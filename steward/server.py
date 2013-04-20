"""
.. module:: server
   :synopsis: Steward server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Steward server

"""
import logging
import re
import traceback
import types
import inspect
import zmq
from datetime import datetime
from threading import Thread
from multiprocessing.pool import ThreadPool
from multiprocessing.queues import Empty
from multiprocessing import Queue
from . import streams
from . import tasks

LOG = logging.getLogger(__name__)

class Server(Thread):
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
    starting : bool
        True during the startup process of running the server
    conf : dict
        The configuration dictionary
    event_handlers : dict
        Mapping of event names to list of handlers
    tasklist : :py:class:`steward.tasks.TaskList`
        The tasklist loaded by the server
    pool : :py:class:`multiprocessing.pool.ThreadPool`
        A threadpool for running ``@threaded`` extensions

    """
    _pubstream = None
    _stream = None

    def __init__(self, conf):
        super(Server, self).__init__()
        self.running = False
        self.starting = False
        self.conf = conf
        self.event_handlers = []
        self.tasklist = tasks.TaskList()
        self.pool = None
        self._start_methods = []
        self._apply_extensions(conf['extension_mods'])
        self._queue = None
        self._active_commands = []
        self._background_cmds = []

    def handle_message(self, msg):
        """
        Handle a client message and return a response

        Parameters
        ----------
        msg : dict
            The command passed up by the client

        """
        command = msg.get('cmd')
        # If the command exists on the Server object, run that
        try:
            attr_list = command.split('.')
            method = self
            for attr in attr_list:
                method = getattr(method, attr)
            
            if getattr(method, '__public__', False):
                value = method(*msg.get('args', []), **msg.get('kwargs', {}))
                retval = {'val':value}
            else:
                raise AttributeError('{} is not public!'.format(command))
        except Exception as e:
            LOG.exception("Error running %s" % command)
            retval = {'exc':traceback.format_exc()}
        finally:
            return retval #pylint: disable=W0150

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
        for pattern, handler in self.event_handlers:
            match = pattern.match(name)
            if match:
                if pattern.groups:
                    retval = handler(self, data, *match.groups())
                else:
                    retval = handler(self, data)
                if retval is True:
                    LOG.info("Sending event %s has been blocked by "
                        "event handler %s", name, handler.__name__)
                    return
        self._pubstream.send(name, data)

    def _handle_async(self, uid, msg):
        """
        Handle a client message and send a response

        Parameters
        ----------
        uid : str
            The uid of the client
        msg : dict
            The command passed up by the client

        """
        command_key = (msg, datetime.now())
        self._active_commands.append(command_key)
        retval = self.handle_message(msg)
        self._active_commands.remove(command_key)
        self._queue.put((uid, retval))

    def start(self):
        # we have to create the thread pool from the Main thread
        self.pool = ThreadPool(processes=self.conf['worker_threads'])
        super(Server, self).start()
    
    def initialize_streams(self):
        """Initialize the zmq streams"""
        if self._stream is None:
            # This socket accepts commands from multiple clients at a time
            self._stream = streams.default_stream(self.conf['stream'],
                self.conf['server_socket'], zmq.ROUTER, True)

        if self._pubstream is None:
            # This socket publishes events to clients
            self._pubstream = streams.default_stream(self.conf['stream'],
                self.conf['server_channel_socket'], zmq.PUB, True)

    def run(self):
        """Listen for client commands and process them"""
        try:
            self.starting = True
            if self.pool is None:
                self.pool = ThreadPool(processes=self.conf['worker_threads'])
            self._queue = Queue()
            self.tasklist.pool = self.pool
            self.tasklist.start()
            self.initialize_streams()
            LOG.info("Starting server")
            for meth in self._start_methods:
                meth(self)
            self.running = True
            self.starting = False
            while self.running:
                try:
                    uid = 's'
                    msg = {}
                    uid, msg = self._stream.recv(timeout=0.1)
                    LOG.info("Got client command: %s" % msg)
                    self.pool.apply_async(self._handle_async, (uid, msg))
                except zmq.ZMQError:
                    pass

                try:
                    uid, response = self._queue.get(block=False)
                    self._stream.send(uid, response)
                except Empty:
                    pass

        finally:
            self.stop()
            self.close()
            LOG.info("Server stopped")

    def close(self):
        """
        Close the server's threads and streams

        This is not thread-safe!

        """
        if self.pool:
            self.pool.close()
            self.pool.terminate()
        if self._queue:
            self._queue.close()
        if self._stream:
            self._stream.close()

    def stop(self):
        """Stop the server"""
        self.running = False
        self.tasklist.stop()

    def _apply_extensions(self, mods):
        """
        Apply extensions modules

        Parameters
        ----------
        self : object
            The instance to apply the extensions to
        mods : list
            List of modules to load the extensions from

        """
        for mod in mods:
            members = inspect.getmembers(mod, callable)
            for name, member in members:
                if name.startswith('_'):
                    continue

                if name == 'on_start':
                    self._start_methods.append(member)
                    continue

                # If this is a task, add it to the tasklist
                if isinstance(member, tasks.Task):
                    bound_task = types.MethodType(member, self, type(self))
                    self.tasklist.add(bound_task)
                # If this is an event handler, add it to the event_handlers
                elif hasattr(member, '__sub_event__'):
                    self.event_handlers.append(
                        (re.compile(member.__sub_event__), member))
                elif hasattr(member, '__public__'):
                    name = name.lower()
                    if hasattr(self, name):
                        attr = getattr(self, name)
                        if hasattr(attr, '__doc__'):
                            desc = attr.__doc__
                        else:
                            desc = str(attr)
                        raise Exception("Server already has extension {}: {}"
                        .format(name, desc))

                    if inspect.isclass(member):
                        instance = member(self)
                        setattr(instance, '__server__', self)
                        setattr(self, name, instance)
                    else:
                        bound_method = types.MethodType(member, self, Server)
                        setattr(self, name, bound_method)

        # Order the event handlers by priority
        self.event_handlers.sort(key=lambda x:x[1].__priority__)
