"""
.. module:: scripts
   :synopsis: Command line entry points

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Command line entry points

"""
import time
import pprint
import logging
from . import config

LOG = logging.getLogger(__name__)

def start_server():
    """Start a steward server"""
    cli = ServerCLI()
    cli.start()

def client_repl():
    """Start an interactive steward client"""
    cli = ClientREPL()
    cli.start()

def client_call():
    """Make a single call with a client"""
    cli = ClientCLI()
    cli.run()

def client_listen():
    """Listen for one or more events and print them out"""
    cli = ListenClientCLI()
    cli.start()

class ServerCLI(config.CMDLineOptionsParserMixin):
    """Load configs and start the steward server"""
    def start(self):
        """Load configs and start the steward server"""
        conf = self.get_config(True)
        from . import server
        srv = server.Server(conf)
        try:
            srv.run()
        except KeyboardInterrupt:
            pass

class ClientREPL(config.CMDLineOptionsParserMixin):
    """Starts an interactive client"""
    def start(self):
        """Starts an interactive client"""
        from . import client
        conf = self.get_config(False)
        cli = client.StewardREPL()
        cli.start(conf)

class ListenClientCLI(config.CMDLineOptionsParserMixin):
    """Subscribe to one or more channels"""
    def __init__(self):
        self.channels = None

    def options(self, parser):
        parser.add_argument('channels', metavar='CHANNEL', nargs='+',
            help='Channel to listen to')

    def configure(self, args):
        self.channels = args['channels']

    def start(self):
        """Subscribe to one or more channels"""
        from . import client
        conf = self.get_config(False)
        c = client.Client(conf)
        c.sub_callback = self._on_msg
        for channel in self.channels:
            c.sub(channel)
        while True:
            try:
                time.sleep(10000)
            except KeyboardInterrupt:
                break

    def _on_msg(self, name, data):
        """Callback for events"""
        print "EVENT: {}".format(name)
        pprint.pprint(data)

class ClientCLI(config.CMDLineOptionsParserMixin):
    """Runs a single client command"""
    def __init__(self):
        self.cmd = None
        self.args = []
        self.kwargs = {}

    def options(self, parser):
        parser.add_argument('cmd', metavar='CMD',
                   help='Command to run')
        parser.add_argument('args', metavar='ARG', nargs='*',
                   help='Argument for the command')

    def configure(self, args):
        self.cmd = args['cmd']
        for arg in args['args']:
            if '=' in arg:
                split = arg.split('=')
                self.kwargs[split[0]] = split[1]
            else:
                self.args.append(arg)

    def run(self):
        """Run the client command"""
        from . import client
        conf = self.get_config(False)
        c = client.Client(conf)
        retval = c.cmd(self.cmd, *self.args, **self.kwargs)
        if 'exc' in retval:
            print retval['exc']
        else:
            pprint.pprint(retval['val'])
