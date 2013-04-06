"""
.. module:: tests
   :synopsis: Common utilities for tests

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Common utilities for tests

"""
from tornado import gen
import inspect
import functools

class AsyncTestGeneratorMetaclass(type):
    """
    A metaclass for constructing asynchronous tests
    
    Any TestCase that has this as the __metaclass__ can use the ``yield
    gen.Task`` syntax for their tests. Any test that uses that must put
    ``self.stop()`` at the end of the test case. The metaclass will enforce
    this when your test is loaded.

    Notes
    -----
    Here's an example::

        class TestAsynchronous(unittest.TestCase):
            __metaclass__ = AsyncTestGeneratorMetaclass
        
            def test_asynchronous_call(self):
                retval = yield gen.Task(_do_something_asynchronous)
                self.assertTrue(retval)
                self.stop()

    """
    def __new__(mcs, name, bases, props):
        def async_wrapper(wrapped):
            """Generate an asynchronous test from this method"""
            source = inspect.getsource(wrapped)
            if source.split()[-1].strip() != "self.stop()":
                raise Exception("Asynchronous tests must end with self.stop()!"
                                " [%s]" % wrapped.__name__)

            @functools.wraps(wrapped)
            def wrapper(self):
                """Wrap a gen.engine test"""
                gen.engine(wrapped)(self)
                self.wait()
            return wrapper

        for propname, prop in props.items():
            if not propname.startswith("test") or not inspect.isfunction(prop):
                continue
            if not prop.__doc__:
                raise Exception("Bitch!  Write some fucking docstrings "
                                "on your tests! [%s]" % propname)
            if inspect.isgeneratorfunction(prop):
                props[propname] = async_wrapper(prop)
        return super(AsyncTestGeneratorMetaclass, mcs).__new__(mcs,
                                                    name, bases, props)
