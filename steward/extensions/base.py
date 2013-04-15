"""
.. module:: base
   :synopsis: Basic extensions for the server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Basic extensions for the server

"""
import inspect
import time
import logging
from steward import public, invisible, private

LOG = logging.getLogger(__name__)

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
    self.publish(channel, kwargs)
    return True

@invisible
def commands(self):
    """List all available server commands"""
    lines = [(name, doc) for name, doc in _visible_members(self)]
    return lines

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
def sleep(self, t=1):
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
    def running(self):
        """Get the list of tasks currently being run"""
        running_tasks = '\n'.join(["{}: {}".format(t.name, d.isoformat())
            for t, d in self.server.tasklist.running_tasks])
        return running_tasks

    @public
    def schedule(self):
        """Get the list of scheduled tasks"""
        schedule = '\n'.join(["{}: {}".format(t.name, t.next_exec.isoformat())
            for t in self.server.tasklist.tasks])
        return schedule

def _run_in_bg(self, command, *args, **kwargs):
    """Run a command and log any exceptions"""
    try:
        command(*args, **kwargs)
    except:
        LOG.exception("Error while running in the background!")

@private
def background(self, command, *args, **kwargs):
    """
    Run an asynchronous command in the background

    Use this when you want to start a command in a non-blocking way and do
    not care about the return value.

    Parameters
    ----------
    command : callable
        The function to call

    """
    fxn_args = [self, command] + list(args)
    self.pool.apply_async(_run_in_bg, fxn_args, kwargs)
