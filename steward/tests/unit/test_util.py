"""
.. module:: test_util
   :synopsis: Test methods in :py:mod:`steward.util`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test methods in :py:mod:`steward.util`

"""
import unittest
import time
from mock import MagicMock
from threading import Thread, RLock
from steward import util

class ExpectedException(Exception):
    """Exception that we expect to see raised"""

class TestUtil(unittest.TestCase):
    """Test methods in :py:mod:`steward.util`"""

    def test_serialize_runs_fxn(self):
        """Functions decorated with @serialize should still be called"""
        @util.serialize
        def my_fxn():
            """Dummy function that returns a constant"""
            return 'foobar'
        retval = my_fxn()
        self.assertEqual(retval, 'foobar')

    def test_serialize_queues_fxns(self):
        """@serialize should queue calls to a function"""
        result_list = []
        @util.serialize
        def sleeper(arg):
            """Dummy function that sleeps"""
            result_list.append(arg)
            time.sleep(0.1)

        t1 = Thread(target=lambda:sleeper('a'))
        t1.daemon = True
        t2 = Thread(target=lambda:sleeper('b'))
        t2.daemon = True
        t1.start()
        t2.start()
        self.assertEquals(result_list, ['a'])

    def test_non_blocking_serialize(self):
        """Non blocking @serialize should return immediately"""
        @util.serialize(blocking=False)
        def sleeper():
            """Dummy function that sleeps"""
            time.sleep(0.2)
            return "sleeper returned"

        t = Thread(target=sleeper)
        t.daemon = True
        t.start()
        time.sleep(0.01)
        retval = sleeper()
        self.assertTrue(retval is False)

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
