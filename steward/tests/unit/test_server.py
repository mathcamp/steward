"""
.. module:: test_server
   :synopsis: Tests for :py:mod:`steward.server`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Tests for :py:mod:`steward.server`

"""
from mock import MagicMock
from steward.util import event_handler, public
from steward import tests

class ServerMods(object):
    """Test server extension module"""
    def on_start(self, server):
        """Start method callback for a server extension"""
        server.ran_on_start = True

    @public
    def ping(self, server):
        """Public function in a server extension"""
        return 'pong'

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

class TestCommands(tests.BaseTest):
    """Tests for :py:mod:`steward.server`"""
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
        retval = self.call_server('ping')
        self.assert_result_equal(retval, 'pong')

    def test_ext_init(self):
        """The server should store the on_start methods from extensions"""
        self.assertEqual(len(self.server._start_methods), 1)
