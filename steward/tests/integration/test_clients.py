"""
.. module:: test_clients
   :synopsis: Test the client-server interface

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test the client-server interface

"""
from multiprocessing import Queue
from mock import MagicMock
from steward import client
from steward.util import public
from . import util

class ServerMods(object):
    """Test server extension module"""
    @public
    def ping(self, server):
        """Simple server call"""
        return 'pong'

class TestClients(util.IntegrationTest):
    """Test the client-server interface"""
    @classmethod
    def setUpClass(cls):
        super(TestClients, cls).setUpClass()
        cls.config['extension_mods'].append(ServerMods())

    def setUp(self):
        super(TestClients, self).setUp()
        self.client = client.Client(self.config)

    def tearDown(self):
        super(TestClients, self).tearDown()
        self.client.close()

    def test_client_call_server(self):
        """Client should be able to call server extensions"""
        result = self.client.cmd('ping')
        self.assert_result_equal(result, 'pong')
    
    def test_client_sub_event(self):
        """Client should receive subbed events"""
        queue = Queue()
        try:
            self.client.sub('test_event', lambda *args:queue.put(args))
            self.server.publish('test_event', 'trigger')
            result, _ = queue.get(timeout=1)
            self.assertEqual(result, 'test_event')
        finally:
            queue.close()

    def test_client_unsub_event(self):
        """After unsubscribing, client should not receive events"""
        queue = Queue()
        try:
            mock = MagicMock()
            self.client.sub('test_event1', mock)
            self.client.sub('test_event2', lambda *args:queue.put(args))

            self.client.unsub('test_event1')

            self.server.publish('test_event1', 'trigger')
            self.server.publish('test_event2', 'trigger')

            result, _ = queue.get(timeout=1)
            self.assertEqual(result, 'test_event2')
            self.assertFalse(mock.called)
        finally:
            queue.close()
