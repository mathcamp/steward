"""Plugin to prevent pylint from erroring on zmq imports"""
from logilab.astng import MANAGER
from logilab.astng.builder import ASTNGBuilder

def zmq_transform(module):
    """Create a fake zmq module with missing members"""
    if module.name == 'zmq':
        fake = ASTNGBuilder(MANAGER).string_build('''

DEALER = None
ROUTER = None
REQ = None
REP = None
PUB = None
SUB = None
PUSH = None
PULL = None
SUBSCRIBE = None
UNSUBSCRIBE = None
NOBLOCK = None

class ZMQError(Exception):
    pass

import zmq
class MySocket(zmq.Socket):
    setsockopt_string = lambda x, y: None

class Context():
    socket = lambda x: MySocket()

''')
        for property in ('Context', 'DEALER', 'ROUTER', 'REQ', 'REP',
        'PUB', 'SUB', 'PUSH', 'PULL', 'SUBSCRIBE', 'UNSUBSCRIBE',
        'NOBLOCK', 'ZMQError'):
            module.locals[property] = fake.locals[property]

def register(linter):
    """called when loaded by pylint --load-plugins, register our tranformation
    function here
    """
    MANAGER.register_transformer(zmq_transform)
