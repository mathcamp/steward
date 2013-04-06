"""
.. module:: test_extensions
   :synopsis: Test the server extension loading

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test the server extension loading

"""
import threading
import sys
from tornado import gen
from . import util
from steward.util import public, threaded

def unlisted_ping(self, callback=None):
    """server extension with no decorator"""
    callback('pong')

@public
def ping(self, callback=None):
    """server extension with @public decorator"""
    callback('pong')

@public
@threaded
def get_thread(self):
    """Server extension that returns the current thread"""
    return threading.current_thread()

@public
class Foo(object):
    """Namespace within the extension"""
    def __init__(self, server):
        pass
    @public
    def ping(self, callback=None):
        """Public method inside the extension Foo namespace"""
        callback('pong')
    def private_ping(self, callback=None):
        """Private method inside the extension Foo namespace"""
        callback('pong')
    @public
    @threaded
    def get_thread(self):
        """Namespaced extension that returns the current thread"""
        return threading.current_thread()

class TestDecorators(util.IntegrationTest):
    """Test the server extension loading"""
    timeout = 1
    @classmethod
    def setUpClass(cls):
        super(TestDecorators, cls).setUpClass()
        cls.config['extension_mods'].append(sys.modules[__name__])

    def test_public_server_methods(self):
        """Public methods on the server should be callable from client"""
        retval = yield gen.Task(self.call_server, 'ping')
        self.assert_result_equal(retval, 'pong')
        self.stop()

    def test_unlisted_server_methods(self):
        """Unlisted methods on the server should not be callable from client"""
        retval = yield gen.Task(self.call_server, 'unlisted_ping')
        self.assert_result_exc(retval)
        self.stop()

    def test_threaded_decorator(self):
        """Threaded commands should run in a background thread"""
        thread = yield gen.Task(self.server.get_thread) #pylint: disable=E1101
        self.assertTrue(isinstance(thread, threading.Thread))
        self.assertNotEqual(thread, threading.current_thread())
        self.stop()

    def test_namespaced_threaded_decorator(self):
        """Threaded commands in a namespace should run in a background thread"""
        #pylint: disable=E1101
        thread = yield gen.Task(self.server.foo.get_thread)
        self.assertTrue(isinstance(thread, threading.Thread))
        self.assertNotEqual(thread, threading.current_thread())
        self.stop()

    def test_public_namespace(self):
        """Public methods in extension namespaces should be callable"""
        retval = yield gen.Task(self.call_server, 'foo.ping')
        self.assert_result_equal(retval, 'pong')
        self.stop()

    def test_unlisted_namespace(self):
        """Unlisted methods in extension namespaces should not be callable"""
        retval = yield gen.Task(self.call_server, 'foo.private_ping')
        self.assert_result_exc(retval)
        self.stop()

    def test_namespace_not_callable(self):
        """The extension namespace itself should not be callable"""
        retval = yield gen.Task(self.call_server, 'foo')
        self.assert_result_exc(retval)
        self.stop()
