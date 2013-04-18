"""
.. module:: test_server
   :synopsis: Tests for :py:mod:`steward.server`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Tests for :py:mod:`steward.server`

"""
from steward.util import public
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

class TestCommands(tests.BaseTest):
    """Tests for :py:mod:`steward.server`"""
    @classmethod
    def setUpClass(cls):
        super(TestCommands, cls).setUpClass()
        cls.config['extension_mods'].append(ServerMods())

    def test_server_command(self):
        """The server should be able to run commands"""
        retval = self.call_server('ping')
        self.assert_result_equal(retval, 'pong')

    def test_ext_init(self):
        """The server should store the on_start methods from extensions"""
        self.assertEqual(len(self.server._start_methods), 1)
