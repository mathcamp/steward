""" Command line client for Steward """
import types
import getpass

import functools
import inspect
import logging
import requests
import shlex
import subprocess
import traceback
from cmd import Cmd
from pyramid.httpexceptions import exception_response
from pyramid.path import DottedNameResolver


LOG = logging.getLogger(__name__)

DEFAULT_INCLUDES = ['steward.base', 'steward.events', 'steward.tasks']

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
    def start(self, conf):
        """
        Start running the interactive session (blocking)

        Parameters
        ----------
        conf : dict
            Configuration dictionary

        """
        self.identchars += '.'
        self.host = conf['host']
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
                allow_redirects=False)
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
            mod.include_client(self)

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

    def set_cmd(self, name, function):
        """
        Create local bound methods for a remote command

        Parameters
        ----------
        name : str
            The name of the command
        doc : str
            The description/documentation for the command

        """
        function = self.name_resolver.maybe_resolve(function)
        bound_cmd = types.MethodType(repl_command(function), self, StewardREPL)
        setattr(self, 'do_' + name, bound_cmd)

    def rm_cmd(self, name):
        """ Remove a command from the client """
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
        response = requests.post(url, data=kwargs, cookies=self.cookies)
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
        print response.text

    @repl_command
    def do_EOF(self): # pylint: disable=C0103
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
    import sys
    if len(sys.argv) == 1:
        conf_file = '/etc/steward.yaml'
    elif len(sys.argv) == 2:
        conf_file = sys.argv[1]
    else:
        print "Too many arguments!"
        sys.exit(1)
    cli = StewardREPL()
    import yaml
    with open(conf_file, 'r') as infile:
        conf = yaml.load(infile)
    cli.start(conf)
