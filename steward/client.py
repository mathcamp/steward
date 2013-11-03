""" Command line client for Steward """
import functools
import getpass
import inspect
import json
import logging
import os
import shlex
import subprocess
import traceback
import types
from cmd import Cmd
from pprint import pprint
from threading import Thread, Lock

import requests
from pyramid.httpexceptions import exception_response
from pyramid.path import DottedNameResolver


LOG = logging.getLogger(__name__)

DEFAULT_INCLUDES = ['steward.base']


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


class StewardREPL(Cmd):

    """
    Interactive commandline interface

    Attributes
    ----------
    aliases : dict
        Dictionary of aliased commands
    host : str
        The address of the server
    cookies : str
        The cookie dict. Contains credentials.
    running : bool
        True while session is active, False after quitting

    """
    aliases = {}
    running = False
    host = None
    cookies = None
    name_resolver = DottedNameResolver(__package__)
    prompt = '==> '
    request_params = {}
    attr_lock = Lock()

    def initialize(self, conf):
        """
        Prepare the client for action

        Parameters
        ----------
        conf : dict
            Configuration dictionary

        """
        self.identchars += './'
        self.host = conf['host']
        self.request_params = conf.get('request_params', {})
        if 'prompt' in conf:
            self.prompt = conf['prompt']
        self.aliases = {}
        if 'aliases' in conf:
            for alias, longvalue in conf['aliases'].iteritems():
                self.do_alias(alias + ' ' + longvalue)
        self.running = True
        if 'user' in conf:
            username = conf['user']
        else:
            username = raw_input('Username: ')
        if 'pass' in conf:
            password = conf['pass']
        else:
            password = getpass.getpass()
        self._auth(username, password)
        self._load_extensions(DEFAULT_INCLUDES)
        self._load_extensions(conf.get('includes', []))

    def start(self):
        """ Start running the interactive session (blocking) """
        while self.running:
            try:
                self.cmdloop()
            except KeyboardInterrupt:
                print
            except:
                traceback.print_exc()

    def _auth(self, userid, password):
        """ Authenticate the user with the Steward server """
        data = {
            'userid': userid,
            'password': password,
        }
        response = requests.post(self.host + '/auth', data=data,
                                 allow_redirects=False, **self.request_params)
        if response.ok:
            self.cookies = response.cookies
        else:
            raise exception_response(response.status_code)

    def _load_extensions(self, mods):
        """
        Load extensions modules

        Parameters
        ----------
        mods : list
            List of modules or dotted module paths to load the extensions from

        """
        for mod in mods:
            mod = self.name_resolver.maybe_resolve(mod)
            loader = Thread(target=functools.partial(mod.include_client, self))
            loader.daemon = True
            loader.start()

    def help_help(self):
        """Print the help text for help"""
        print "List commands or print details about a command"

    def do_shell(self, arglist):
        """ Run a shell command """
        print subprocess.check_output(shlex.split(arglist))

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

    def set_cmd(self, name, function, wrap=True):
        """
        Create local bound methods for a remote command

        Parameters
        ----------
        name : str
            The name of the command
        doc : str
            The description/documentation for the command
        wrap : bool, optional
            Wrap the method with @repl_command (default True)

        """
        function = self.name_resolver.maybe_resolve(function)
        if wrap:
            function = repl_command(function)
        bound_cmd = types.MethodType(function, self, StewardREPL)
        with self.attr_lock:
            setattr(self, 'do_' + name, bound_cmd)

    def rm_cmd(self, name):
        """ Remove a command from the client """
        with self.attr_lock:
            if hasattr(self, 'do_' + name):
                delattr(self, 'do_' + name)
            if hasattr(self, 'help_' + name):
                delattr(self, 'help_' + name)
            if hasattr(self, 'complete_' + name):
                delattr(self, 'complete_' + name)

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
        with self.attr_lock:
            setattr(self, 'complete_' + command, bound_cmd)

    def cmd(self, uri, **kwargs):
        """
        Run a command on the steward server

        Parameters
        ----------
        uri : str
            The uri path to use
        kwargs : dict
            The parameters to pass up in the request

        """
        if not uri.startswith('/'):
            uri = '/' + uri
        url = self.host + uri
        for key, value in kwargs.items():
            if type(value) not in (int, float, bool, str, unicode):
                kwargs[key] = json.dumps(value)
        response = requests.post(url, data=kwargs, cookies=self.cookies,
                                 **self.request_params)
        if not response.ok:
            try:
                data = response.json()
            except:
                data = None
            kw = {}
            if data is not None:
                kw['detail'] = data['detail']
            raise exception_response(response.status_code, **kw)
        if response.cookies:
            self.cookies.update(response.cookies)
        return response

    @repl_command
    def default(self, *args, **kwargs):
        """
        If there is an unrecognized command, send it to the server and see what
        happens!
        """
        response = self.cmd(*args, **kwargs)
        try:
            pprint(response.json())
        except:
            print response.text

    @repl_command
    def do_EOF(self):  # pylint: disable=C0103
        """Exit"""
        return self.onecmd('exit')

    @repl_command
    def do_exit(self):
        """Exit"""
        self.running = False
        print
        return True

    def emptyline(self):
        pass


def run_client():
    """ Entry point for running the REPL """
    import argparse
    import sys
    import yaml

    parser = argparse.ArgumentParser(description=run_client.__doc__)
    parser.add_argument('-c', default='/etc/steward/client',
                        help="Config file or directory (default %(default)s)")
    parser.add_argument('cmd', nargs='*',
                        help="Run this command, print the output, and exit")

    args = vars(parser.parse_args())
    if not os.path.exists(args['c']):
        print ("Must specify a conf file or directory! "
               "/etc/steward/client/ not found")
        sys.exit(1)

    cli = StewardREPL()
    if os.path.isfile(args['c']):
        with open(args['c'], 'r') as infile:
            conf = yaml.safe_load(infile)
    else:
        conf = {}
        for filename in os.listdir(args['c']):
            with open(os.path.join(args['c'], filename), 'r') as infile:
                conf.update(yaml.safe_load(infile))

    cli.initialize(conf)
    if args['cmd']:
        cli.onecmd(' '.join(args['cmd']))
    else:
        cli.start()
