"""Unit and integration tests"""
from steward import config, server
import unittest

class BaseTest(unittest.TestCase):
    """
    Base class for steward tests
    
    """
    @classmethod
    def setUpClass(cls):
        super(BaseTest, cls).setUpClass()
        cls.config = config.bare_config(None)
        cls.config['extension_mods'] = []

    def setUp(self):
        super(BaseTest, self).setUp()
        self.server = server.Server(self.config)

    def call_server(self, cmd, *args, **kwargs):
        """
        Simulate a client call to the server without actually going through zmq

        Parameters are the same you would pass to
        :py:meth:`steward.client.Client.cmd`

        """
        msg = {'cmd':cmd, 'args':args, 'kwargs':kwargs}
        return self.server.handle_message(msg)

    def assert_result_equal(self, first, second, msg=None):
        """
        Assert that a response from the server is equal to a value

        Parameters
        ----------
        first : object
            The server response
        second : object
            The value to test the server response against
        msg : str, optional
            Message to print if the assertion fails

        """
        self.assertEqual(first.get('val'), second, msg)

    def assert_result_exc(self, result, msg=None):
        """
        Assert that the server response is an exception

        Parameters
        ----------
        result : object
            The server response
        msg : str, optional
            Message to print if the assertion fails

        """
        self.assertTrue('exc' in result, msg)
