"""
.. module:: base
   :synopsis: Basic extensions for the server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Basic extensions for the server

"""
import inspect
import time
from tornado import ioloop
from datetime import timedelta
from steward import public, invisible, threaded

@public
def pub(self, channel, **kwargs):
    """
    Publish an event

    Parameters
    ----------
    channel : str
        The channel to publish on
    
    Notes
    -----
    Converts any kwargs into a dict and publishes the dict as the event data
    object
    
    """
    callback = kwargs.pop('callback')
    self.publish(channel, kwargs)
    callback(True)

@invisible
def commands(self, callback=None):
    """List all available server commands"""
    lines = [(name, doc) for name, doc in _visible_members(self)]
    callback(lines)

def _visible_members(object):
    """Find all visible members of an object"""
    for name, member in inspect.getmembers(object):
        if name.startswith('_'):
            continue
        if not getattr(member, '__public__', False):
            continue
        if getattr(member, '__invisible__', False):
            continue
        if not callable(member):
            for subname, doc in _visible_members(member):
                yield name + '.' + subname, doc
            continue
        doc = getattr(member, '__doc__', '')
        if doc is None:
            doc = ''
        yield name, doc

@invisible
def sleep(self, t=1, callback=None):
    """
    Sleep then return

    Parameters
    ----------
    t : float
        Number of seconds to sleep

    """
    ioloop.IOLoop.instance().add_timeout(timedelta(seconds=float(t)),
        lambda: callback(True))

@invisible
@threaded
def sync_sleep(self, t=1):
    """
    Sleep in a background thread, then return

    Parameters
    ----------
    t : float
        Number of seconds to sleep

    """
    time.sleep(float(t))
    return True

@public
class Tasks(object):
    """Wrapper for task-specific calls"""
    def __init__(self, server):
        self.server = server

    @public
    def running(self, callback=None):
        """Get the list of tasks currently being run"""
        running_tasks = '\n'.join(["{}: {}".format(t.name, d.isoformat())
            for t, d in self.server.tasklist.running_tasks])
        callback(running_tasks)

    @public
    def schedule(self, callback=None):
        """Get the list of scheduled tasks"""
        schedule = '\n'.join(["{}: {}".format(t.name, t.next_exec.isoformat())
            for t in self.server.tasklist.tasks])
        callback(schedule)
