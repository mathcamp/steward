"""
.. module:: base
   :synopsis: Basic extensions for the server

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Basic extensions for the server

"""
import inspect
import subprocess
import time
import logging
from datetime import datetime
from steward import public, invisible, private

LOG = logging.getLogger(__name__)

@public
def pub(self, channel, **kwargs):
    """
    pub(channel, **kwargs)

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

@public
def sh(self, *args, **kwargs):
    """
    sh(*args, **kwargs)

    Run a shell command on the server

    """
    arglist = list(args) + [k + '=' + v for k, v in kwargs.iteritems()]
    return subprocess.check_output(arglist)

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
        if not hasattr(member, '__public__'):
            continue
        if getattr(member, '__invisible__', False):
            continue
        if not inspect.ismethod(member):
            for subname, doc in _visible_members(member):
                yield name + '.' + subname, doc
        if not getattr(member, '__public__', False):
            continue
        if not inspect.isfunction(member) and not inspect.ismethod(member) \
        and hasattr(member, '__call__'):
            doc = getattr(member.__call__, '__doc__', None) or ''
        else:
            doc = getattr(member, '__doc__', None) or ''
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

@private
class Tasks(object):
    """Wrapper for task-specific calls"""
    def __init__(self, server):
        self.server = server

    @public
    def running(self):
        """
        tasks.running()

        Get the list of tasks currently being run

        """
        running_tasks = '\n'.join(["{}: {}".format(t.name, d.isoformat())
            for t, d in self.server.tasklist.running_tasks])
        return running_tasks

    @public
    def schedule(self):
        """
        tasks.schedule()

        Get the list of scheduled tasks

        """
        now = datetime.now()
        schedule = '\n'.join(["{}: -{}".format(t.name, str(t.next_exec - now))
            for t in self.server.tasklist.tasks])
        return schedule

def _run_in_bg(self, command, *args, **kwargs):
    """Run a command and log any exceptions"""
    try:
        key = (datetime.now(), command, args, kwargs)
        self._background_cmds.append(key)
        command(*args, **kwargs)
    except:
        LOG.exception("Error while running in the background!")
    finally:
        self._background_cmds.remove(key)

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

def _fxn_signature(cmd, *args, **kwargs):
    """Construct a string representation of a function call"""
    arglist = ', '.join([str(arg) for arg in args])
    if kwargs:
        kwarglist = ', '.join(["{}={}".format(k, v) for k, v
            in kwargs.iteritems()])
        arglist += ', ' + kwarglist
    return cmd + '(' + arglist + ')'

@public
def status(self):
    """
    status()

    Display the currently running commands and tasks

    """
    now = datetime.now()
    cmds = ['Commands', '--------']
    for msg, date in self._active_commands:
        delta = now - date
        msg_call = _fxn_signature(msg['cmd'], *msg['args'], **msg['kwargs'])
        cmds.append(str(delta) + "  " + msg_call)

    cmds.append('')
    cmds.append('Background')
    cmds.append('----------')
    for date, cmd, args, kwargs in self._background_cmds:
        delta = now - date
        msg_call = _fxn_signature(cmd.__name__, *args, **kwargs)
        cmds.append(str(delta) + "  " + msg_call)

    cmds.append('')
    cmds.append('Tasks')
    cmds.append('-----')
    for task, date in self.tasklist.running_tasks:
        delta = now - date
        cmds.append(str(delta) + "  " + task.name)

    return '\n'.join(cmds)

@private
def get_bool(self, string):
    """
    Convert a string argument into a boolean

    Parameters
    ----------
    string : basestring or bool
        The argument passed in from a client or a bool (if a bool this method
        will just return that value)

    Returns
    -------
    the_bool : bool

    Raises
    ------
    TypeError
        If the string is unrecognized or the argument is not already a string or bool

    """
    if isinstance(string, bool):
        return string
    if not isinstance(string, basestring):
        raise TypeError("get_bool must be called with a string!")
    string = string.strip().lower()

    if string == "y" or string == "yes" or string == "t" or string == "true":
        return True
    elif string == "n" or string == "no" or string == "f" or string == "false":
        return False
    raise TypeError("Unrecognized boolean type %s" % string)
