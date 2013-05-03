"""
.. module:: test_util
   :synopsis: Test methods in :py:mod:`steward.util`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test methods in :py:mod:`steward.util`

"""
import unittest
from mock import MagicMock
from threading import RLock
from steward import util

class ExpectedException(Exception):
    """Exception that we expect to see raised"""

class TestUtil(unittest.TestCase):
    """Test methods in :py:mod:`steward.util`"""

    def test_synchronized_method(self):
        """@synchronized methods should use default lock on class"""
        class Foo(object):
            """Dummy object"""
            __lock__ = None
            @util.synchronized
            def foobar(self):
                """noop"""

        Foo.__lock__ = MagicMock()
        f = Foo()
        f.foobar()
        Foo.__lock__.__enter__.assert_any_call()

    def test_synchronized_method_with_lock(self):
        """@synchronized should accept a lock as an argument"""
        lock = MagicMock()
        class Foo(object):
            """Dummy object"""
            @util.synchronized(lock)
            def foobar(self):
                """noop"""

        f = Foo()
        f.foobar()
        lock.__enter__.assert_any_call()

    def test_default_lock(self):
        """@synchronized classes should get a default RLock"""
        @util.synchronized
        class Foo(object):
            """Dummy object"""
            def foobar(self):
                """noop"""
        f = Foo()
        self.assertTrue(hasattr(f, '__lock__'))
        self.assertEqual(type(getattr(f, '__lock__')), type(RLock()))

    def test_synchronized_class(self):
        """@synchronized classes should use default lock on class"""
        @util.synchronized
        class Foo(object):
            """Dummy object"""
            def foobar(self):
                """noop"""
        f = Foo()
        f.__lock__ = MagicMock()
        f.foobar()
        f.__lock__.__enter__.assert_any_call()

    def test_synchronized_class_instance_lock(self):
        """@synchronized classes with a manual __lock__ should use that lock"""
        @util.synchronized
        class Foo(object):
            """Dummy object"""
            def __init__(self):
                self.__lock__ = MagicMock()
            def foobar(self):
                """noop"""
        f = Foo()
        f.foobar()
        f.__lock__.__enter__.assert_any_call()

    def test_synchronized_class_with_lock(self):
        """@synchronized classes should accept a lock as an argument"""
        lock = MagicMock()
        @util.synchronized(lock)
        class Foo(object):
            """Dummy object"""
            def foobar(self):
                """noop"""
        f = Foo()
        f.foobar()
        lock.__enter__.assert_any_call()
