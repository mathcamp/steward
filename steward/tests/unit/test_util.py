"""
.. module:: test_util
   :synopsis: Test methods in :py:mod:`steward.util`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test methods in :py:mod:`steward.util`

"""
import unittest
import time
from threading import Thread
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
