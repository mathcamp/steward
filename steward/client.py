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
    partial_callback : callable
        This attribute will be called when the client receives a partial
        response from the server

    """
    def __init__(self, conf=None):
        if conf is None:
            conf = config.load_config(False)
        self.conf = conf
        self.meta = {}
        c = zmq.Context()
        socket = c.socket(zmq.DEALER)

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
        self.partial_callback = None
        self._nonce = 0

    def _create_nonce(self):
        """ Construct a nonce """
        self._nonce += 1
        return self._nonce - 1

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
        arguments for the command.

        .. warning::
            This method is not thread-safe!

        Returns
        -------
        retval : dict
            The dictionary response from the server

        """
        nonce = self._create_nonce()
        self._stream.send({'cmd':command, 'args':args, 'kwargs':kwargs,
            'meta':self.meta, 'nonce':nonce})
        while True:
            resp = self._stream.recv()
            if resp['nonce'] != nonce:
                continue
            if resp['type'] == 'partial':
                if self.partial_callback is not None:
                    # pylint: disable=E1102
                    self.partial_callback(resp)
            else:
                return resp

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
    aliases = {}
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
        self.prompt = conf['prompt']
        self.client = Client(conf)
        self.client.partial_callback = self.on_partial
        self.client.format = 'text'
        self.client.meta.update(conf['meta'])
        self.client.sub_callback = self._sub_callback
        self.aliases = {}
        for alias, longvalue in conf['aliases'].iteritems():
            self.do_alias(alias + ' ' + longvalue)
        self.running = True
        commands = self.client.cmd('commands').get('response')
        self.set_server_commands(commands)
        self._apply_extensions(conf['extension_mods'])
        while self.running:
            try:
                self.cmdloop()
            except KeyboardInterrupt:
                print
            except:
                traceback.print_exc()

    @property
    def meta(self):
        """ Access the client's meta dictionary """
        return self.client.meta

    def _apply_extensions(self, mods):
        """
        Apply extensions modules

        Parameters
        ----------
        mods : list
            List of modules to load the extensions from

        """
        on_start_methods = []
        for mod in mods:
            members = inspect.getmembers(mod, callable)
            for name, member in members:
                if name.startswith('_'):
                    continue

                if name == 'on_client_start':
                    on_start_methods.append(member)
                    continue

                ext_name = getattr(member, '__client_ext__', False)
                if ext_name:
                    bound_method = types.MethodType(repl_command(member), self,
                        StewardREPL)
                    if isinstance(ext_name, basestring):
                        name = ext_name
                    setattr(self, 'do_' + name, bound_method)

        for method in on_start_methods:
            method(self)

    def help_help(self):
        """Print the help text for help"""
        print "List commands or print details about a command"

    def do_shell(self, arglist):
        """ Run a shell command """
        print subprocess.check_output(shlex.split(arglist))

    def on_partial(self, resp):
        """ Print out the partial response """
        print resp['desc']

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
            pprint.pprint(self.meta)
        else:
            args = arglist.split()
            key, val = args
            self.meta[key] = json.loads(val)

    @repl_command
    def do_client_version(self):
        """ Get the current version of steward running on the client """
        # pylint: disable=F0401,E0611
        from steward.__version__ import __version__
        print __version__

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

    def set_server_commands(self, commands):
        """ Attach a list of commands from the server to this class """
        for element in commands:
            self.set_cmd(element['name'], element['doc'])
            if 'complete' in element:
                self.set_autocomplete(element['name'], element['complete'])

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

    def set_autocomplete(self, command, args):
        """ Set a command to autocomplete the given arguments """
        def wrapper(self, text, line, begidx, endidx):
            """ A wrapper for a simple autocomplete implementation """
            # We have to do a little magic here because cmd.py apparently
            # doesn't count '-' as part of a word
            while line[begidx-1] not in ' ,':
                begidx -= 1
            full_text = line[begidx:endidx]
            prefix = len(full_text) - len(text)
            matches = [arg[prefix:] for arg in args if
                arg.startswith(full_text)]
            if not matches:
                matches.append(text)
            return matches
        bound_cmd = types.MethodType(wrapper, self, StewardREPL)
        setattr(self, 'complete_' + command, bound_cmd)

    def run_cmd(self, command, *args, **kwargs):
        """
        Run a command on the server and return the output

        """
        retval = self.client.cmd(command, *args, **kwargs)
        if retval['type'] == 'response':
            return retval['response']
        elif retval['type'] == 'error':
            raise Exception('Server error: %s' % retval['error'])
        else:
            raise TypeError('Unrecognized response: %s' % retval)

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
        if retval['type'] == 'error':
            print retval['error']
        elif retval['type'] == 'response':
            if retval['response'] is None:
                pass
            elif isinstance(retval['response'], basestring):
                print retval['response']
            else:
                pprint.pprint(retval['response'])
        else:
            print "Unrecognized return type {}!".format(retval['type'])

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
