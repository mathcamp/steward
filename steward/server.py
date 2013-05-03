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
import threading
import signal
import time
from datetime import datetime
from collections import defaultdict
from multiprocessing.pool import ThreadPool
from multiprocessing.queues import Empty
from multiprocessing import Queue
from . import streams
from . import tasks

LOG = logging.getLogger(__name__)

class Server(threading.Thread):
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
        A threadpool for running client commands

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
        self._formatters = defaultdict(dict)
        self._apply_extensions(conf['extension_mods'])
        self._queue = None
        self._active_commands = []
        self._background_cmds = []
        # Mapping of uids to threads
        self._client_cmds = {}

    @property
    def uid(self):
        """
        The uid for the client making the active request

        Returns
        -------
        uid : str

        Notes
        -----
        This should only be called from extensions. If this is called in an
        event handler or a task, it will return None.

        When requests come in, we tag their handler thread with the uid. This
        method pulls that uid off of the active thread.

        """
        cur = threading.current_thread()
        return getattr(cur, '_uid', None)

    @property
    def client(self):
        """
        A configuration dictionary for the current client

        Returns
        -------
        config : dict

        Notes
        -----
        This is subject to the same constraints as
        :py:meth:`steward.server.Server.uid`

        """
        cur = threading.current_thread()
        return getattr(cur, '_client_meta', {})

    @property
    def nonce(self):
        """
        The nonce of the current request

        Returns
        -------
        nonce : int

        Notes
        -----
        This is subject to the same constraints as
        :py:meth:`.Server.uid`

        """
        cur = threading.current_thread()
        return getattr(cur, '_nonce')

    def get_formatter(self, command, format):
        """
        Get a specific formatter

        Parameters
        ----------
        command : str
            The command to format
        format : str
            The format to use

        Returns
        -------
        formatter : callable
            Takes two arguments, the server and the output. May be None if no
            formatter is found.

        """
        return self._formatters.get(format, {}).get(command)

    def handle_message(self, uid, msg):
        """
        Handle a client message and return a response

        Parameters
        ----------
        msg : dict
            The command passed up by the client

        """
        command = msg.get('cmd')
        cur = threading.current_thread()
        try:
            setattr(cur, '_uid', uid)
            setattr(cur, '_client_meta', msg.get('meta', {}))
            setattr(cur, '_nonce', msg['nonce'])

            attr_list = command.split('.')
            method = self
            for attr in attr_list:
                method = getattr(method, attr)
            
            if getattr(method, '__public__', False):
                value = method(*msg.get('args', []), **msg.get('kwargs', {}))

                format = self.client.get('format', 'raw')
                formatter = self.get_formatter(command, format)
                if formatter is not None:
                    value = formatter(self, value)

                retval = {
                    'type':'response',
                    'response':value,
                    'nonce':msg['nonce'],
                }
            else:
                raise AttributeError('{} is not public!'.format(command))
        except Exception as e:
            LOG.exception("Error running %s" % command)
            retval = {
                'type':'error',
                'error':traceback.format_exc(),
                'nonce':msg['nonce'],
            }
        finally:
            delattr(cur, '_uid')
            delattr(cur, '_client_meta')
            delattr(cur, '_nonce')
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
                try:
                    if pattern.groups:
                        retval = handler(self, data, *match.groups())
                    else:
                        retval = handler(self, data)
                    if retval is True:
                        LOG.info("Sending event %s has been blocked by "
                            "event handler %s", name, handler.__name__)
                        return
                except:
                    LOG.exception("Error running event handler!")
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
        self._client_cmds[uid] = threading.current_thread()
        command_key = (msg, datetime.now())
        self._active_commands.append(command_key)
        retval = self.handle_message(uid, msg)
        self._active_commands.remove(command_key)
        # If the client has made another request since we started running
        # this one, don't try to send the response to that client
        if self._client_cmds[uid] != threading.current_thread():
            uid = None
        self._queue.put((uid, retval))

    def partial(self, msg_type, desc=''):
        """
        Send a partial response to a client

        Parameters
        ----------
        msg_type : str
            Short string indicating some information about the partial reply
        desc : str, optional
            Human-readable description about this partial reply (default '')

        """
        # If the client has made another request since we started running
        # this one, don't try to send the response to that client
        uid = self.uid
        if self._client_cmds[uid] != threading.current_thread():
            uid = None
        retval = {
            'type':'partial',
            'partial':msg_type,
            'desc':desc,
            'nonce':self.nonce,
        }
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

    def _try_respond(self):
        """ Send all queued responses to clients, if any """
        try:
            while True:
                uid, response = self._queue.get(block=False)
                try:
                    if uid is not None:
                        self._stream.send(uid, response)
                except TypeError:
                    LOG.exception("Error sending response")
                    retval = {'exc':traceback.format_exc()}
                    self._stream.send(uid, retval)
        except Empty:
            pass

    def run(self):
        """Listen for client commands and process them"""
        try:
            self.starting = True
            if self.pool is None:
                self.pool = ThreadPool(processes=self.conf['worker_threads'])
            self._queue = Queue()
            self.initialize_streams()
            LOG.info("Starting server...")
            for meth in self._start_methods:
                meth(self)
            self.tasklist.pool = self.pool
            self.tasklist.start()

            # Register to shut down gracefully on the SIGQUIT signal
            signal.signal(signal.SIGQUIT, lambda *_: self.stop())

            self.running = True
            self.starting = False
            LOG.info("Started")
            try:
                while self.running:
                    try:
                        uid = 's'
                        msg = {}
                        uid, msg = self._stream.recv(timeout=0.1)
                        LOG.info("Got client command: %s" % msg)
                        self.pool.apply_async(self._handle_async, (uid, msg))
                    except zmq.ZMQError:
                        pass

                        self._try_respond()
            except KeyboardInterrupt:
                self.stop()

            LOG.info("Shutting down")
            while self._active_commands or self._background_cmds:
                if self._active_commands:
                    LOG.info("Waiting for active commands: %s",
                        self._active_commands)
                if self._background_cmds:
                    LOG.info("Waiting for background commands: %s",
                        self._background_cmds)
                for _ in range(10):
                    time.sleep(1)
                    self._try_respond()

            self._try_respond()

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
                elif hasattr(member, '__format_type__'):
                    self._formatters[member.__format_type__]\
                        [member.__format_cmd__] = member
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
