"""
.. module:: tasks
   :synopsis: Periodic tasks that get run on the server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Periodic tasks that get run on the server

"""
import logging
from croniter import croniter
from datetime import datetime, timedelta
from tornado import ioloop, gen
from .util import threaded

LOG = logging.getLogger(__name__)

def task(*args, **kwargs):
    """
    Convenience decorator for creating a :py:class:`~steward.tasks.Task`

    This allows you to create tasks inside of a server extension module like
    so::

        @task('*/5 * * * *')
        def spam_clients(self):
            self.publish('spam', 'spamspamspamspam')
            
    
    """
    def decorator(fxn):
        """The decorator for the task function"""
        return Task(fxn, *args, **kwargs)
    return decorator

class Task(object):
    """
    A periodic task that is run on the server

    Parameters
    ----------
    fxn : callable
        The function to be run at intervals

    Attributes
    ----------
    next_exec
    name : str
        Human-readable name of the task
    fxn : callable
        The function to be run at intervals

    Notes
    -----
    There are several ways to specify the schedule for the task to be run on. It accepts standard cron format::
        
        mytask = Task(do_something, '*/15 1-6,4-8 * * *')

    You can pass the cron args in as separate args::

        mytask = Task(do_something, '*/15', '1-6,4-8', '*', '*', '*')

    You can pass the cron args in as keywords::

        mytask = Task(do_something, minutes='*/15', hours='1-6,4-8')

    Or you can define your own scheduler. It must be a callable that accepts a
    :py:class:`~datetime.datetime` and returns the next
    :py:class:`~datetime.datetime` that the task will be run::

        def every_10_seconds(dt):
            return dt + datetime.timedelta(seconds=10)

        mytask = Task(do_something, every_10_seconds)

    Note that if the custom scheduler function ever returns ``None``, the task
    will be removed from the :py:class:`~steward.tasks.TaskList`. So to define
    a task that gets run once, 15 minutes after startup::

        class TerminatingTaskSchedule(object):
            def __init__(self, num_runs, delta):
                self.num_runs = num_runs
                self.delta = delta

            def __call__(self, dt):
                if self.num_runs <= 0:
                    return None
                self.num_runs -= 1
                return dt + self.delta

        mytask = Task(do_something, TerminatingTaskSchedule(1, datetime.timedelta(minutes=15)))

    """
    def __init__(self, fxn, *args, **kwargs):
        self.fxn = fxn
        self.name = "{}.{}".format(fxn.__module__, fxn.__name__)
        self._next_exec = None
        cron = None
        if len(args) == 1 and len(kwargs) == 0:
            arg = args[0]
            if callable(arg):
                self._calc_next_exec = lambda: arg(datetime.now())
            else:
                # '0 0 * * *'
                cron = croniter(arg)
        elif len(args) == 5 and len(kwargs) == 0:
            # 0, 0, '*', '*', '*'
            cron = croniter(' '.join([str(arg) for arg in args]))
        elif len(args) == 0:
            # minutes=0, hours=0
            minutes = str(kwargs.pop('minutes', '*'))
            hours = str(kwargs.pop('hours', '*'))
            dom = str(kwargs.pop('dom', '*'))
            months = str(kwargs.pop('months', '*'))
            dow = str(kwargs.pop('dow', '*'))
            if len(kwargs) != 0:
                raise TypeError("Unrecognized keyword arguments {}"
                .format(kwargs))
            cron = croniter(' '.join((minutes, hours, dom, months, dow)))
        else:
            raise TypeError("Task arguments invalid! "
                "{} {}".format(args, kwargs))
            
        if cron:
            self._calc_next_exec = lambda: cron.get_next(datetime)

    @property
    def next_exec(self):
        """
        The datetime when this task next should be run

        The first time this is called it calculates the next scheduled run
        based on the current time. All subsequent calls retrieve that cached
        value until :py:meth:`~steward.tasks.Task.reset_next_exec` is called.

        """
        if self._next_exec is None:
            self._next_exec = self._calc_next_exec()
        return self._next_exec

    def reset_next_exec(self):
        """Recalculates the next scheduled run based on the current timestamp"""
        self._next_exec = self._calc_next_exec()

    def __call__(self, *args, **kwargs):
        try:
            return self.fxn(*args, **kwargs)
        except Exception as e:
            LOG.error("Error running %s", self.name)
            LOG.exception(e)
    
class TaskList(object):
    """
    Container that runs schedule tasks

    Attributes
    ----------
    tasks : list
        List of :py:class:`~steward.tasks.Task`s
    running_tasks : list
        List of (:py:class:`~steward.tasks.Task`,
        :py:class:`datetime.datetime`) of tasks that are currently
        running. The datetime is the time it started running.

    """
    def __init__(self):
        self.tasks = []
        self.running_tasks = []

    def add(self, new_task):
        """
        Add a task to the TaskList. This may be called before or after
        :py:meth:`~steward.tasks.TaskList.start`.

        Parameters
        ----------
        new_task : :py:class:`~steward.tasks.Task`
            The task to add

        """
        self.tasks.append(new_task)
        self.tasks.sort(key=lambda x:x.next_exec)

    def _sleep(self, duration, callback=None):
        """Shortcut for asynchronous sleep"""
        ioloop.IOLoop.instance().add_timeout(duration, callback)

    @gen.engine
    def _run_task(self, run_task):
        """Run a task"""
        task_key = (run_task, datetime.now())
        self.running_tasks.append(task_key)
        yield gen.Task(threaded(run_task))
        self.running_tasks.remove(task_key)
        
    @gen.engine
    def start(self):
        """Start running the scheduled tasks. Non-blocking."""
        while True:
            if len(self.tasks) == 0:
                yield gen.Task(self._sleep, timedelta(seconds=5))
                continue

            delta = self.tasks[0].next_exec - datetime.now()
            if delta.total_seconds() > 0:
                yield gen.Task(self._sleep, delta)
                continue
            cur_task = self.tasks[0]
            cur_task.reset_next_exec()

            if cur_task.next_exec is None:
                # Remove it from the task list
                self.tasks.pop(0)

            self.tasks.sort(key=lambda x:x.next_exec)
            ioloop.IOLoop.instance().add_callback(cur_task)
            # Sleep for a tiny amount of time so we never get stuck here
            yield gen.Task(self._sleep, timedelta(seconds=0.01))
