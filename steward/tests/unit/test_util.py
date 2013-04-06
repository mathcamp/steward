"""
.. module:: test_util
   :synopsis: Test methods in :py:mod:`steward.util`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test methods in :py:mod:`steward.util`

"""
from tornado import testing, gen
from steward import util, tests

class ExpectedException(Exception):
    """Exception that we expect to see raised"""

class TestUtil(testing.AsyncTestCase):
    """Test methods in :py:mod:`steward.util`"""
    __metaclass__ = tests.AsyncTestGeneratorMetaclass

    def test_serialize_runs_fxn(self):
        """Functions decorated with @serialize should still be called"""
        @util.serialize
        def my_fxn(callback=None):
            """Dummy function that returns a constant"""
            callback('foobar')
        retval = yield gen.Task(my_fxn)
        self.assertEqual(retval, 'foobar')

        self.stop()

    def test_serialize_queues_fxns(self):
        """@serialize should queue calls to a function"""
        result_list = []
        @util.serialize
        def no_callback(arg, callback=None):
            """Dummy function that never calls the callback"""
            result_list.append(arg)
        no_callback('a', callback=None)
        no_callback('b', callback=None)
        # Since the function never calls the callback, the function will never
        # return. So the serialization should think that 'a' is still running
        # when we call it on 'b'
        self.assertEquals(result_list, ['a'])

    def test_non_blocking_serialize(self):
        """Non blocking @serialize should return immediately"""
        @util.serialize(blocking=False)
        def dummy(callback=None):
            """Dummy function that never calls the callback"""
        dummy(callback=None)
        retval = yield gen.Task(dummy)
        self.assertTrue(retval is False)
        
        self.stop()
