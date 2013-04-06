"""
.. module:: util
   :synopsis: Utility methods for integration tests

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Utility methods for integration tests

"""
from mock import MagicMock
from tornado import testing, ioloop, gen
from steward import server, config, tests
from zmq import eventloop

eventloop.ioloop.install()

class IntegrationTest(testing.AsyncTestCase):
    """
    Base class for integration tests that starts a server
    
    Attributes
    ----------
    timeout : int
        How long to wait for an asynchronous test case to run before raising an
        exception

    """
    __metaclass__ = tests.AsyncTestGeneratorMetaclass
    timeout = 2
    @classmethod
    def setUpClass(cls):
        super(IntegrationTest, cls).setUpClass()
        cls.config = config.bare_config(None)
        cls.config['server_socket'] = "ipc:///tmp/steward-test"
        cls.config['server_channel_socket'] = "ipc:///tmp/steward-channel-test"
        cls.config['extension_mods'] = []

    def get_new_ioloop(self):
        return ioloop.IOLoop.instance()

    def wait(self, *args, **kwargs):
        """Allow tweaking the default timeout"""
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout
        return super(IntegrationTest, self).wait(*args, **kwargs)


    def setUp(self):
        super(IntegrationTest, self).setUp()
        self.server = server.Server(self.config)

    def tearDown(self):
        super(IntegrationTest, self).tearDown()
        self.server.stop()

    @gen.engine
    def call_server(self, cmd, *args, **kwargs):
        """
        Simulate a client call to the server

        Parameters are the same you would pass to
        :py:meth:`steward.client.Client.cmd`

        """
        callback = kwargs.pop('callback')
        stream = MagicMock()
        msg = {'cmd':cmd, 'args':args, 'kwargs':kwargs}
        stream.send.side_effect = yield gen.Callback('send')
        self.server.client_callback(stream, 'uid', msg)
        retval = yield gen.Wait('send')
        (_, value), _ = retval
        callback(value)

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
