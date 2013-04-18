"""
.. module:: test_events
   :synopsis: Test event subscription and handling

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test event subscription and handling

"""
from mock import patch
from steward import tests
from steward.util import event_handler
from steward.server import Server


class ServerMods(object):
    """Test server extension module"""

    @event_handler(r'test_event', priority=50)
    def handle_test_event_low(self, server, data):
        """An event handler in a server extension"""
        data['handler_val'] = 2

    @event_handler(r'test_event', priority=10)
    def handle_test_event_high(self, server, data):
        """A high-priority event handler in a server extension"""
        data['handler_val'] = 1

    @event_handler(r'stopped_event')
    def handle_stopped_event(self, server, data):
        """An event handler that returns True"""
        return True

    @event_handler(r'event.*')
    def handle_regex_event(self, server, data):
        """An event handler that matches a regex"""
        data['handled'] = True

    @event_handler(r'arg_event/(.*)')
    def handle_regex_event_args(self, server, data, param):
        """An event handler that matches a regex"""
        data['handled'] = param

class TestEvents(tests.BaseTest):
    """Test event subscription and handling"""

    @classmethod
    def setUpClass(cls):
        super(TestEvents, cls).setUpClass()
        cls.config['extension_mods'].append(ServerMods())

    def setUp(self):
        super(TestEvents, self).setUp()
        patch.object(Server, '_pubstream').start()
        self.stream = Server._pubstream

    def tearDown(self):
        super(TestEvents, self).tearDown()
        patch.stopall()

    def test_ordered_handlers(self):
        """Events should be handled in priority order"""
        self.server.publish('test_event', {})
        expected_value = {'handler_val':2}
        self.stream.send.assert_called_once_with('test_event',
            expected_value)

    def test_event_stopper(self):
        """Event should not be sent if handler returns True"""
        self.server.publish('stopped_event', {})
        self.assertFalse(self.stream.send.called)

    def test_event_regexes(self):
        """Subscriptions to regexes should receive events"""
        self.server.publish('event_wgarbl', {})
        expected_value = {'handled':True}
        self.stream.send.assert_called_once_with('event_wgarbl', expected_value)

    def test_event_regex_args(self):
        """Subscriptions to regexes with groups should get arguments"""
        self.server.publish('arg_event/hihi', {})
        expected_value = {'handled':'hihi'}
        self.stream.send.assert_called_once_with('arg_event/hihi',
            expected_value)
