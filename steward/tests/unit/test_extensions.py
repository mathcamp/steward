"""
.. module:: test_extensions
   :synopsis: Test the server extension loading

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test the server extension loading

"""
import sys
from steward import tests
from steward.util import public, private, formatter

def unlisted_ping(self):
    """server extension with no decorator"""
    return 'pong'

@formatter('text', 'formatme')
def format_ping(output):
    """ Output formatter """
    return 'text'

@formatter('complex', 'formatme')
def meta_echo_formatter(output, meta):
    """ Complex output formatter """
    return meta

@formatter('raw', 'formatme')
def raw_formatme(output):
    """ Output formatter """
    return 'raw'

@public
def formatme(self):
    """ Dummy call """
    return

@public
def echo_meta(self):
    """ Call that returns the client's meta dict """
    return self.client

@public
def ping(self):
    """server extension with @public decorator"""
    return 'pong'

@private
def private_ping(self):
    """Private server extension"""
    return 'pong'

@public
def private_ping_wrapper(self):
    """Public wrapper around the private ping"""
    return self.private_ping()

@public
class Foo(object):
    """Namespace within the extension"""
    def __init__(self, server):
        pass
    @public
    def ping(self):
        """ Public method inside the extension Foo namespace """
        return 'pong'
    def private_ping(self):
        """ Private method inside the extension Foo namespace """
        return 'pong'
    def __call__(self):
        """ Make Foo a callable """
        return 'bar'

@private
class PrivateFoo(object):
    """ A private namespace """
    def __init__(self, server):
        pass
    @public
    def ping(self):
        """ Public method inside a private namespace """
        return 'pong'

    def __call__(self):
        """ Make PrivateFoo a callable """
        return 'bar'

class TestDecorators(tests.BaseTest):
    """Test the server extension loading"""
    timeout = 1
    @classmethod
    def setUpClass(cls):
        super(TestDecorators, cls).setUpClass()
        cls.config['extension_mods'].append(sys.modules[__name__])

    def test_public_server_methods(self):
        """Public methods on the server should be callable from client"""
        retval = self.call_server('ping')
        self.assert_result_equal(retval, 'pong')

    def test_unlisted_server_methods(self):
        """Unlisted methods on the server should not be callable from client"""
        retval = self.call_server('unlisted_ping')
        self.assert_result_exc(retval)

    def test_private_not_callable(self):
        """Private methods on the server should not be callable from client"""
        retval = self.call_server('private_ping')
        self.assert_result_exc(retval)

    def test_private_callable_from_server(self):
        """Private methods should be attached to server"""
        retval = self.call_server('private_ping_wrapper')
        self.assert_result_equal(retval, 'pong')

    def test_public_namespace(self):
        """Public methods in extension namespaces should be callable"""
        retval = self.call_server('foo.ping')
        self.assert_result_equal(retval, 'pong')

    def test_unlisted_namespace(self):
        """Unlisted methods in extension namespaces should not be callable"""
        retval = self.call_server('foo.private_ping')
        self.assert_result_exc(retval)

    def test_namespace_callable(self):
        """The extension namespace itself should be callable"""
        retval = self.call_server('foo')
        self.assert_result_equal(retval, 'bar')

    def test_private_namespace_not_callable(self):
        """ Private namespaces should not be callable """
        retval = self.call_server('privatefoo')
        self.assert_result_exc(retval)

    def test_private_namespace_method_callable(self):
        """ Public methods in private namespaces should be callable"""
        retval = self.call_server('privatefoo.ping')
        self.assert_result_equal(retval, 'pong')

    def test_default_raw_format(self):
        """ If no format specified, the 'raw' format is used """
        retval = self.call_server('formatme')
        self.assert_result_equal(retval, 'raw')

    def test_formatter(self):
        """ The output formatter that matches the 'meta' dict formats the output """
        self.meta['format'] = 'text'
        retval = self.call_server('formatme')
        self.assert_result_equal(retval, 'text')

    def test_formatter_meta_arg(self):
        """ Output formatters can receive the 'meta' dict as an arg """
        self.meta['format'] = 'complex'
        retval = self.call_server('formatme')
        self.assert_result_equal(retval, self.meta)

    def test_extension_access_meta_dict(self):
        """ Extension have access to the 'meta' dict """
        self.meta['unique'] = 'hihi'
        retval = self.call_server('echo_meta')
        self.assert_result_equal(retval, self.meta)
