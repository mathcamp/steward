"""
.. module:: test_server
   :synopsis: Tests for :py:mod:`steward.server`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Tests for :py:mod:`steward.server`

"""
from tornado import gen
from mock import MagicMock
from . import util
from steward.util import event_handler, public

class ServerMods(object):
    """Test server extension module"""
    def init(self, server):
        """Init method for a server extension"""
        server.ran_init = True

    @public
    def ping(self, server, callback=None):
        """Public function in a server extension"""
        callback('pong')

    @event_handler('test_event', priority=50)
    def handle_test_event(self, server, data):
        """An event handler in a server extension"""
        data['handler_val'] = 2

class MoreServerMods(object):
    """Another test server extension module"""
    @event_handler('test_event', priority=10)
    def handle_test_event(self, server, data):
        """A high-priority event handler in a server extension"""
        data['handler_val'] = 1

    @event_handler('stopped_event')
    def handle_stopped_event(self, server, data):
        """An event handler that returns True"""
        return True

class TestCommands(util.IntegrationTest):
    """Tests for :py:mod:`steward.server`"""
    timeout = 1
    @classmethod
    def setUpClass(cls):
        super(TestCommands, cls).setUpClass()
        cls.config['extension_mods'].extend((ServerMods(), MoreServerMods()))

    def test_ordered_handlers(self):
        """Events should be handled in priority order"""
        stream_mock = self.server._pubstream = MagicMock()
        self.server.publish('test_event', {})
        expected_value = {'handler_val':2}
        stream_mock.send.assert_called_once_with('test_event',
            expected_value)

    def test_event_stopper(self):
        """Event should not be sent if handler returns True"""
        stream_mock = self.server._pubstream = MagicMock()
        self.server.publish('stopped_event', {})
        self.assertFalse(stream_mock.send.called)

    def test_server_command(self):
        """The server should be able to run commands"""
        retval = yield gen.Task(self.call_server, 'ping')
        self.assert_result_equal(retval, 'pong')
        self.stop()

    def test_ext_init(self):
        """The server should apply the init methods inside extension modules"""
        self.assertTrue(hasattr(self.server, 'ran_init'))
