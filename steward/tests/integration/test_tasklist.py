"""
.. module:: test_tasklist
   :synopsis: Tests for :py:class:`steward.tasks.TaskList`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Tests for :py:class:`steward.tasks.TaskList`

"""
import sys
from datetime import timedelta
from mock import MagicMock
from tornado import gen, ioloop
from .util import IntegrationTest
from steward.tasks import task, Task

@task('0 0 * * *')
def echo_server_task(self):
    """This task just returns the instance it is bound to"""
    return self

class TaskListTest(IntegrationTest):
    """Tests for :py:class:`steward.tasks.TaskList`"""
    timeout = 1
    @classmethod
    def setUpClass(cls):
        super(TaskListTest, cls).setUpClass()
        # Add this file as a module
        cls.config['extension_mods'].append(sys.modules[__name__])

    def _get_task(self, name):
        """Find a bound task on the server by name"""
        for server_task in self.server.tasklist.tasks:
            if server_task.fxn.__name__ == name:
                return server_task
        raise AttributeError("Could not find task {}".format(name))

    def test_task_args(self):
        """Tasks are called with the server as an argument"""
        echo_task = self._get_task('echo_server_task')
        retval = echo_task()
        self.assertEqual(retval, self.server)

    def test_task_scheduling(self):
        """A task is run at the times it is scheduled"""
        mock = MagicMock(__name__='MagicMock')
        scheduled_task = Task(mock, lambda dt: dt + timedelta(seconds=0.01))
        self.server.tasklist.add(scheduled_task)
        self.server.tasklist.start()
        ioloop.IOLoop.instance().add_timeout(timedelta(seconds=0.025),
            (yield gen.Callback('sleep')))
        yield gen.Wait('sleep')
        self.assertEqual(mock.call_count, 2)
        self.stop()

    def test_task_removal(self):
        """A task is removed from the TaskList if the next time is None"""
        mock = MagicMock(__name__='MagicMock')
        calls = [1]
        def _task_fxn(dt):
            """A task function that return None on the second call"""
            if len(calls) > 0:
                calls.pop()
                return dt
            else:
                return None
        single_task = Task(mock, _task_fxn)
        self.server.tasklist.add(single_task)
        self.server.tasklist.start()
        ioloop.IOLoop.instance().add_timeout(timedelta(seconds=0.01),
            (yield gen.Callback('sleep')))
        yield gen.Wait('sleep')
        with self.assertRaises(AttributeError):
            self._get_task('_task_fxn')

        self.stop()

    def test_late_task_runs(self):
        """If a task is 'late', it still gets run"""
        mock = MagicMock(__name__='MagicMock')
        scheduled_task = Task(mock, lambda dt: dt - timedelta(minutes=3))
        self.server.tasklist.add(scheduled_task)
        self.server.tasklist.start()
        ioloop.IOLoop.instance().add_timeout(timedelta(seconds=0.01),
            (yield gen.Callback('sleep')))
        yield gen.Wait('sleep')
        mock.assert_any_call()
        self.stop()
