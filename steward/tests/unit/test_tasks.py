"""
.. module:: test_tasks
   :synopsis: Unit tests for :py:mod:`steward.tasks`

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Unit tests for :py:mod:`steward.tasks`

"""
import unittest
from mock import MagicMock
from steward import tasks

class TestTasks(unittest.TestCase):
    """Unit tests for :py:mod:`steward.tasks`"""
    
    def test_single_string_cron(self):
        """Single-string cron format should work"""
        task = tasks.Task(lambda: None, '0 0 * * *')
        self.assertIsNotNone(task.next_exec)

    def test_custom_fxn_cron(self):
        """Passing a custom function for cron scheduling should work"""
        task = tasks.Task(lambda: None, lambda dt:dt)
        self.assertIsNotNone(task.next_exec)

    def test_multi_argument_cron(self):
        """Individual arguments for cron format should work"""
        task = tasks.Task(lambda: None, '0', '0', '*', '*', '*')
        self.assertIsNotNone(task.next_exec)

    def test_int_arguments_cron(self):
        """Individual cron arguments may be ints"""
        task = tasks.Task(lambda: None, 0, 0, '*', '*', '*')
        self.assertIsNotNone(task.next_exec)

    def test_keyword_argument_cron(self):
        """Keyword arguments for cron format should work"""
        task = tasks.Task(lambda: None, minutes='0', hours='0')
        self.assertIsNotNone(task.next_exec)

    def test_int_keyword_argument_cron(self):
        """Keyword arguments for cron format may be ints"""
        task = tasks.Task(lambda: None, minutes=0, hours=0)
        self.assertIsNotNone(task.next_exec)

    def test_invalid_keyword_argument_cron(self):
        """Invalid keywords for cron format should fail"""
        with self.assertRaises(TypeError):
            tasks.Task(lambda: None, seconds=0, minutes=0)

    def test_invalid_num_arguments_cron(self):
        """Invalid number of arguments for cron format should fail"""
        with self.assertRaises(TypeError):
            tasks.Task(lambda: None, '0', '0', '*', '*')

    def test_task_wrapper(self):
        """Task decorator should pass through to the Task class"""
        myfxn = lambda: None
        task = tasks.task('* * * * *')(myfxn)
        self.assertTrue(isinstance(task, tasks.Task))
        self.assertIsNotNone(task.next_exec)

    def test_task_call(self):
        """Running task should run wrapped function"""
        mock = MagicMock(__name__='MagicMock')
        task = tasks.Task(mock, minutes=0)
        task()
        mock.assert_any_call()
