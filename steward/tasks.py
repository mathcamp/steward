""" Extension for running scheduled tasks """
import time
from datetime import timedelta, datetime

import logging
from croniter import croniter
from threading import Thread


LOG = logging.getLogger(__name__)

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

class TaskList(Thread):
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
    running : bool
        True if the tasklist is running

    """
    def __init__(self):
        super(TaskList, self).__init__()
        self.daemon = True
        self.tasks = []
        self.running_tasks = []
        self.running = True

    def add(self, new_task):
        """
        Add a task to the TaskList

        Parameters
        ----------
        new_task : :py:class:`~steward.tasks.Task`
            The task to add

        """
        self.tasks.append(new_task)
        self.tasks.sort(key=lambda x:x.next_exec)

    def _run_task(self, task_to_run):
        """Run a task"""
        task_key = (task_to_run, datetime.now())
        self.running_tasks.append(task_key)
        try:
            task_to_run()
        finally:
            self.running_tasks.remove(task_key)

    def run(self):
        """Start running the scheduled tasks"""
        while self.running:
            if len(self.tasks) == 0:
                time.sleep(1)
                continue

            delta = self.tasks[0].next_exec - datetime.now()
            if delta.total_seconds() > 0:
                time.sleep(delta.total_seconds())
                continue
            cur_task = self.tasks[0]
            cur_task.reset_next_exec()

            if cur_task.next_exec is None:
                # Remove it from the task list
                self.tasks.pop(0)

            self.tasks.sort(key=lambda x:x.next_exec)
            thread = Thread(target=lambda:self._run_task(cur_task))
            thread.daemon = True
            thread.start()

    def stop(self):
        """Stop running the tasklist"""
        self.running = False


def tasks_running(request):
    """ Endpoint for retrieving the running tasks """
    tasks = []
    for task, dt in request.tasklist.running_tasks:
        tasks.append((task.name, time.mktime(dt.timetuple())))
    return tasks

def tasks_schedule(request):
    """ Endpoint for retrieving the task schedule """
    now = datetime.now()
    tasks = []
    for task in request.tasklist.tasks:
        tasks.append((task.name, (task.next_exec - now).total_seconds()))
    return tasks

def do_tasks_running(client):
    """ Get this list of currently running tasks """
    response = client.cmd('tasks/running').json()
    lines = []
    now = datetime.now()
    for name, ts in response:
        dt = datetime.fromtimestamp(ts)
        delta = now - dt
        lines.append("{}: {}".format(name, delta))
    print '\n'.join(lines)

def do_tasks_schedule(client):
    """ Get the current task schedule """
    response = client.cmd('tasks/schedule').json()
    lines = []
    for name, sec in response:
        td = timedelta(seconds=sec)
        lines.append("{}: -{}".format(name, td))
    print '\n'.join(lines)

def _add_task(config, fxn, *args, **kwargs):
    """ Config directive for adding a task """
    config.registry.tasklist.add(Task(fxn, *args, **kwargs))

def _tasklist(request):
    """ Request method to access the tasklist """
    return request.registry.tasklist

def include_client(client):
    """ Set the client commands """
    client.set_cmd('tasks.running', do_tasks_running)
    client.set_cmd('tasks.schedule', do_tasks_schedule)

def includeme(config):
    """ Configure the app """
    config.registry.tasklist = TaskList()
    config.registry.tasklist.start()
    config.add_directive('add_task', _add_task)
    config.add_request_method(_tasklist, name='tasklist', reify=True)

    config.add_route('tasks_schedule', '/tasks/schedule')
    config.add_route('tasks_running', '/tasks/running')
    config.add_view(tasks_running, route_name='tasks_running', renderer='json')
    config.add_view(tasks_schedule, route_name='tasks_schedule',
                    renderer='json')
