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
from datetime import datetime, timedelta
from steward import public, invisible, private, formatter

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
def version(self):
    """ Get the current version of steward """
    from steward.__version__ import __version__
    return __version__

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
    return list(_visible_members(self, self))

def _visible_members(self, object):
    """Find all visible members of an object"""
    for name, member in inspect.getmembers(object):
        if name.startswith('_'):
            continue
        if not hasattr(member, '__public__'):
            continue
        if getattr(member, '__invisible__', False):
            continue
        if not inspect.ismethod(member):
            for element in _visible_members(self, member):
                element['name'] = name + '.' + element['name']
                yield element
        if not getattr(member, '__public__', False):
            continue
        if not inspect.isfunction(member) and not inspect.ismethod(member) \
        and hasattr(member, '__call__'):
            doc = getattr(member.__call__, '__doc__', None) or ''
        else:
            doc = getattr(member, '__doc__', None) or ''
        element = {'name':name, 'doc':doc}

        if name == 'ssh':
            print name
        arg_complete = getattr(object, 'complete_' + name, None)
        if arg_complete:
            element['complete'] = arg_complete(self)

        yield element

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

@formatter('text', 'tasks.running')
def format_running(self, output):
    """ Format the output of tasks.running """
    lines = []
    for name, ts in output:
        dt = datetime.fromtimestamp(ts)
        lines.append("{}: {}".format(name, dt.isoformat()))
    return '\n'.join(lines)

@formatter('text', 'tasks.schedule')
def format_schedule(self, output):
    """ Format the output of tasks.schedule """
    lines = []
    for name, sec in output:
        td = timedelta(sec)
        lines.append("{}: -{}".format(name, td))
    return '\n'.join(lines)

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
        tasks = []
        for task, dt in self.server.tasklist.running_tasks:
            tasks.append((task.name, time.mktime(dt.timetuple())))
        return tasks

    @public
    def schedule(self):
        """
        tasks.schedule()

        Get the list of scheduled tasks

        """
        now = datetime.now()
        tasks = []
        for task in self.server.tasklist.tasks:
            tasks.append((task.name, (task.next_exec - now).total_seconds()))
        return tasks

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

@formatter('text', 'status')
def format_status(self, output):
    """ Format the output of status """
    lines = ['Commands', '--------']
    for fxn, seconds in output['commands']:
        lines.append("{}  {}".format(timedelta(seconds=seconds), fxn))
    lines.append('')
    lines.append('Background')
    lines.append('----------')
    for fxn, seconds in output['background']:
        lines.append("{}  {}".format(timedelta(seconds=seconds), fxn))
    lines.append('')
    lines.append('Tasks')
    lines.append('-----')
    for fxn, seconds in output['tasks']:
        lines.append("{}  {}".format(timedelta(seconds=seconds), fxn))
    return '\n'.join(lines)

@public
def status(self):
    """
    status()

    Display the currently running commands and tasks

    """
    now = datetime.now()
    retval = {}
    retval['commands'] = []
    for msg, date in self._active_commands:
        delta = now - date
        msg_call = _fxn_signature(msg['cmd'], *msg['args'], **msg['kwargs'])
        retval['commands'].append((msg_call, delta.total_seconds()))

    retval['background'] = []
    for date, cmd, args, kwargs in self._background_cmds:
        delta = now - date
        msg_call = _fxn_signature(cmd.__name__, *args, **kwargs)
        retval['background'].append((msg_call, delta.total_seconds()))

    retval['tasks'] = []
    for task, date in self.tasklist.running_tasks:
        delta = now - date
        retval['tasks'].append((task.name, delta.total_seconds()))

    return retval

@private
def get_bool(self, string):
    """
    Convert a string argument into a boolean

    Parameters
    ----------
    string : basestring or bool
        The argument passed in from a client or a bool (if this is a bool the
        method is a no-op)

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

    if string in ('y', 'yes', 't', 'true', '1'):
        return True
    elif string in ('n', 'no', 'f', 'false', '0'):
        return False
    raise TypeError("Unrecognized boolean type %s" % string)

@private
def get_list(self, string):
    """
    Convert a comma-delimited string argument into a list

    Parameters
    ----------
    string : basestring or list
        The argument passed in from a client or a list (if not a string this
        method is a no-op)

    Returns
    -------
    the_list : list

    """
    if isinstance(string, basestring):
        return string.split(',')
    else:
        return string
