"""
.. module:: util
   :synopsis: Utility methods for integration tests

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Utility methods for integration tests

"""
import time
from steward import tests

class IntegrationTest(tests.BaseTest):
    """
    Base class for integration tests that starts a server
    
    """
    @classmethod
    def setUpClass(cls):
        super(IntegrationTest, cls).setUpClass()
        cls.config['server_socket'] = "ipc:///tmp/steward-test"
        cls.config['server_channel_socket'] = "ipc:///tmp/steward-channel-test"

    def setUp(self):
        super(IntegrationTest, self).setUp()
        self.server.daemon = True
        self.server.start()
        while not self.server.running:
            time.sleep(0.01)

    def tearDown(self):
        super(IntegrationTest, self).tearDown()
        self.server.stop()
