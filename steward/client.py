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
import pprint
import logging
import shlex
from . import config
from . import util
from . import streams

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
    subscriptions : dict
        Mapping of event names to callbacks
    open : bool
        True while streams are open, False after calling ``close()``

    """
    def __init__(self, conf=None):
        if conf is None:
            conf = config.load_config()
        self.conf = conf
        c = zmq.Context()
        socket = c.socket(zmq.REQ)

        if conf['server'] is not None:
            zmq.ssh.tunnel_connection(socket, conf['server_socket'],
                conf['server'])
        else:
            socket.connect(conf['server_socket'])

        self._stream = util.load_class(conf['stream'],
            'steward.streams')(socket)

        self.subscriptions = {}
        self._callback = None
        self._substream = None
        self.open = True

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
        self._substream = streams.default_stream(self.conf['stream'],
            self.conf['server_channel_socket'], zmq.SUB, False)
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
        self._stream.send({'cmd':command, 'args':args, 'kwargs':kwargs})
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
        self.subscriptions[name](name, data)

    def sub(self, channel, callback):
        """
        Subscribe to a certain event

        Parameters
        ----------
        channel : str
            Name of event to receive messages about
        callback : callable
            A function with the signature of callback(name, data)

        """
        self._create_substream()
        self._substream.sub(channel)
        self.subscriptions[channel] = callback
        # It takes a short amount of time for pyzmq to actually subscribe
        time.sleep(0.05)

    def unsub(self, channel):
        """
        Unsubscribe from a certain event

        Parameters
        ----------
        channel : str
            Name of event to stop receiving messages about

        """
        self._create_substream()
        del self.subscriptions[channel]
        self._substream.unsub(channel)

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

    """
    client = None
    commands = []
    aliases = {}
    prompt = '8==D '
    running = False
    def start(self, conf):
        """
        Start running the interactive session (blocking)

        Parameters
        ----------
        conf : dict
            Configuration dictionary

        """
        self.client = Client(conf)
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

    @repl_command
    def do_sub(self, channel):
        """
        Subscribe to a channel
        
        Parameters
        ----------
        channel : str
            Name of event channel to subscribe to

        """
        self.client.sub(channel, self._sub_callback)

    @repl_command
    def do_subs(self):
        """List all subscribed channels"""
        print ', '.join(self.client.subscriptions.keys())

    @repl_command
    def do_unsub(self, channel):
        """
        Unsubscribe from a channel
        
        Parameters
        ----------
        channel : str
            Name of event channel to unsubscribe from

        """
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
