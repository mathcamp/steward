"""
.. module:: client
   :synopsis: Clients for connecting to the server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Clients for connecting to the server

"""
import time
import zmq
import zmq.ssh
import traceback
import threading
import cmd
import functools
import inspect
import types
import subprocess
import pprint
import logging
import shlex
import json
from . import config
from . import util

LOG = logging.getLogger(__name__)

class Client(object):
    """
    Basic client for connecting to Steward server

    Parameters
    ----------
    conf : dict, optional
        Configuration dictionary (default loads from config file)

    Attributes
    ----------
    conf : dict
        Configuration dictionary
    meta : dict
        The client meta dict that is passed up to the server with each call
    subscriptions : dict
        Mapping of event names to callbacks
    open : bool
        True while streams are open, False after calling ``close()``
    sub_callback : callable
        A function with the signature of callback(name, data)

    """
    def __init__(self, conf=None):
        if conf is None:
            conf = config.load_config()
        self.conf = conf
        self.meta = {}
        c = zmq.Context()
        socket = c.socket(zmq.REQ)

        if conf['server'] is not None:
            zmq.ssh.tunnel_connection(socket, conf['server_socket'],
                conf['server'])
        else:
            socket.connect(conf['server_socket'])

        self._stream = util.load_class(conf['stream'],
            'steward.streams')(socket)

        self.sub_callback = None
        self._callback = None
        self._substream = None
        self.open = True

    @property
    def format(self):
        """ Get the data format that the server will be returning """
        return self.meta.get('format', 'raw')

    @format.setter
    def format(self, format):
        """
        Set the return format for the server to use

        Parameters
        ----------
        format : str
            Usually one of 'text', 'html', or 'raw' (the default)

        """
        self.meta['format'] = format

    def _create_substream(self):
        """
        Create the subscription stream

        Returns
        -------
        stream : :py:class:`steward.streams.BaseStream`
            A stream created with a SUB socket

        """
        if self._substream is not None:
            return
        c = zmq.Context()
        socket = c.socket(zmq.SUB)
        if self.conf['server'] is not None:
            zmq.ssh.tunnel_connection(socket,
                self.conf['server_channel_socket'], self.conf['server'])
        else:
            socket.connect(self.conf['server_channel_socket'])

        self._substream = util.load_class(self.conf['stream'],
            'steward.streams')(socket)

        thread = threading.Thread(target=self._poll)
        thread.daemon = True
        thread.start()

    def _poll(self):
        """Background loop that listens for events"""
        while self.open:
            try:
                name, data = self._substream.recv(timeout=0.1)
            except zmq.ZMQError:
                continue
            self._on_pub(name, data)
        self.close()

    def cmd(self, command, *args, **kwargs):
        """
        Abstract method for running a command on the server

        Parameters
        ----------
        command : str
            Name of the command to run
        
        Notes
        -----
        Any args and kwargs will be serialized and passed up to the server as
        arguments for the command

        Returns
        -------
        retval : dict
            The dictionary response from the server

        """
        self._stream.send({'cmd':command, 'args':args, 'kwargs':kwargs,
            'meta':self.meta})
        return self._stream.recv()

    def _on_pub(self, name, data):
        """
        Callback when client receives a published event

        Parameters
        ----------
        stream : :py:class:`steward.streams.BaseStream`
            The stream this came from
        name : str
            Name of the event that was published
        data : object
            The data that was published with the event
        
        """
        LOG.debug("Received event %s", name)
        if self.sub_callback is not None:
            self.sub_callback(name, data) # pylint: disable=E1102

    def sub(self, prefix):
        """
        Subscribe to a certain event prefix

        Parameters
        ----------
        prefix : str
            Prefix to receive messages about.

        Notes
        -----
        You also need to set the `sub_callback`, otherwise the subscribed
        events won't go anywhere :/

        """
        self._create_substream()
        self._substream.sub(prefix)
        # It takes a short amount of time for pyzmq to actually subscribe
        time.sleep(0.05)

    def unsub(self, prefix):
        """
        Unsubscribe from a certain event prefix

        Parameters
        ----------
        prefix : str
            Prefix to stop receiving messages about

        """
        self._create_substream()
        self._substream.unsub(prefix)

    def close(self):
        """Close active streams"""
        self.open = False
        self._stream.close()
        if self._substream:
            self._substream.close()

def repl_command(fxn):
    """
    Decorator for :py:class:`~steward.clients.StewardREPL` methods
    
    Parses arguments from the arg string and passes them to the method as *args
    and **kwargs.

    """
    @functools.wraps(fxn)
    def wrapper(self, arglist):
        """Wraps the command method"""
        args = []
        kwargs = {}
        if arglist:
            for arg in shlex.split(arglist):
                if '=' in arg:
                    split = arg.split('=')
                    kwargs[split[0]] = split[1]
                else:
                    args.append(arg)
        return fxn(self, *args, **kwargs)
    return wrapper

class StewardREPL(cmd.Cmd):
    """
    Interactive commandline interface

    Attributes
    ----------
    client : :py:class:`~steward.clients.Client`
        The client that is connected to the server
    commands : list
        List of command tuples (name, description) retrieved from server
    aliases : dict
        Dictionary of aliased commands
    prompt : str
        The interactive prompt
    running : bool
        True while session is active, False after quitting
    subscriptions : set
        Set of all the events subscribed to

    """
    client = None
    commands = []
    aliases = {}
    prompt = '8==D '
    running = False
    subscriptions = set()
    def start(self, conf):
        """
        Start running the interactive session (blocking)

        Parameters
        ----------
        conf : dict
            Configuration dictionary

        """
        self.identchars += '.'
        self.client = Client(conf)
        self.client.format = 'text'
        self.client.meta.update(conf['meta'])
        self.client.sub_callback = self._sub_callback
        self.aliases = {}
        for alias, longvalue in conf['aliases'].iteritems():
            self.do_alias(alias + ' ' + longvalue)
        self.running = True
        self.commands = self.client.cmd('commands').get('val')
        for name, docs in self.commands:
            self.set_cmd(name, docs)
        while self.running:
            try:
                self.cmdloop()
            except KeyboardInterrupt:
                print
            except:
                traceback.print_exc()

    def help_help(self):
        """Print the help text for help"""
        print "List commands or print details about a command"

    def do_shell(self, arglist):
        """ Run a shell command """
        print subprocess.check_output(shlex.split(arglist))

    def do_meta(self, arglist):
        """
        meta() or meta(key, val)

        Set a client meta key, or list all values

        Parameters
        ----------
        key : str
            The key for the meta dict
        val : str
            The value for the meta dict (in json format)

        """
        if not arglist:
            pprint.pprint(self.client.meta)
        else:
            args = arglist.split()
            key, val = args
            self.client.meta[key] = json.loads(val)

    @repl_command
    def do_sub(self, channel=''):
        """
        Subscribe to a channel
        
        Parameters
        ----------
        channel : str, optional
            Name of event channel to subscribe to (default all channels)

        """
        self.subscriptions.add(channel)
        self.client.sub(channel)

    @repl_command
    def do_subs(self):
        """List all subscribed channels"""
        copyset = set(self.subscriptions)
        if '' in copyset:
            copyset.remove('')
            copyset.add('<all>')
        print ', '.join(copyset)

    @repl_command
    def do_unsub(self, channel=''):
        """
        Unsubscribe from a channel
        
        Parameters
        ----------
        channel : str, optional
            Name of event channel to unsubscribe from (default the '' channel)

        """
        self.subscriptions.remove(channel)
        self.client.unsub(channel)

    @repl_command
    def do_alias(self, *args, **kwargs):
        """
        Create an alias for another command or print current aliases

        ``alias`` will print the current list of aliases

        ``alias p ping`` will alias the ``p`` command to run ``ping``

        ``alias hi pub greetings myname=stevearc`` will alias the ``hi``
        command to publish an event by the name of 'greetings' with the payload
        of {'myname':'stevearc'}
        
        """
        if len(args) == 0:
            if kwargs:
                raise TypeError("Must call alias with a name and a target")
            else:
                if not self.aliases:
                    print "No aliases"
                else:
                    for name, command in self.aliases.iteritems():
                        print "alias {}='{}'".format(name, command)
                return
        elif len(args) < 2:
            raise TypeError("Must call alias with a name and a target")
        command, tgt = args[:2]
        args = args[2:]
        alias_args = ' '.join(["'" + a + "'" for a in args])
        alias_kwargs = ' '.join(["'" + k + '=' + v + "'" for k, v in
            kwargs.iteritems()])
        full_cmd = ' '.join((tgt, alias_args, alias_kwargs)).strip()
        self.aliases[command] = full_cmd
        def wrapper(self, other_args):
            """Wrap the aliased command"""
            self.onecmd(' '.join((full_cmd, other_args)))
        wrapper.__doc__ = "'{}' is aliased to '{}'".format(command, full_cmd)
        bound_cmd = types.MethodType(wrapper, self, StewardREPL)
        setattr(self, 'do_' + command, bound_cmd)

    def get_names(self):
        return [name for name, _ in inspect.getmembers(self, callable)]

    @repl_command
    def do_browse(self):
        """ Print out the help for all commands """
        for name in self.get_names():
            if not name.startswith('do_'):
                continue
            print name[3:]
            self.do_help(name[3:])
            print '-----------------'

    def set_cmd(self, name, doc):
        """Create local bound methods for a remote command

        Parameters
        ----------
        name : str
            The name of the command
        doc : str
            The description/documentation for the command
        
        """
        @repl_command
        def wrapper(self, *args, **kwargs):
            """Wrapper for the remote command"""
            self._run_server_command(name, *args, **kwargs)
        wrapper.__doc__ = doc
        bound_cmd = types.MethodType(wrapper, self, StewardREPL)
        setattr(self, 'do_' + name, bound_cmd)

    def _run_server_command(self, command, *args, **kwargs):
        """
        Run a command on the server and print the output

        Parameters
        ----------
        command : str
            The name of the command to run

        Notes
        -----
        All arguments and keyword arguments will be passed to the command on
        the server.

        """
        retval = self.client.cmd(command, *args, **kwargs)
        if 'exc' in retval:
            print retval['exc']
        elif retval['val'] is None:
            pass
        elif isinstance(retval['val'], basestring):
            print retval['val']
        else:
            pprint.pprint(retval['val'])

    @repl_command
    def default(self, *args, **kwargs):
        """
        If there is an unrecognized command, send it to the server and see what
        happens!
        """
        if len(args) == 1 and not kwargs:
            if args[0] == 'grow':
                self.prompt = '8==' + self.prompt[1:]
                return

        self._run_server_command(*args, **kwargs)

    @repl_command
    def do_EOF(self): # pylint: disable=C0103
        """Exit"""
        self.running = False
        print
        return True

    def _sub_callback(self, name, data):
        """
        Callback for subscribed events

        Parameters
        ----------
        name : str
            Name of the subscribed event
        data : object
            The event payload

        """
        print "\nEVENT: %s" % name
        if data:
            pprint.pprint(data)

    def emptyline(self):
        pass
