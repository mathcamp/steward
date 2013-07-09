""" A server orchestration framework written as a Pyramid app """
import datetime

import json
import logging
import pyramid.renderers
import requests
import threading
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest, HTTPServerError
from pyramid.request import Request
from pyramid.security import NO_PERMISSION_REQUIRED
from urllib import urlencode

from . import locks

lock = locks.lock # pylint: disable=C0103

LOG = logging.getLogger(__name__)

def cmd(fxn):
    """
    A decorator for marking a view as a Steward command. Used for introspection by the client

    """
    fxn.__steward_cmd__ = True
    return fxn

NO_ARG = object()

def _param(request, name, default=NO_ARG, type=None):
    """
    Access a parameter and perform type conversion

    Parameters
    ----------
    request : :class:`~pyramid.request.Request`
    name : str
        The name of the parameter to retrieve
    default : object, optional
        The default value to use if none is found
    type : object, optional
        The type to convert the argument to

    Raises
    ------
    exc : :class:`~pyramid.httpexceptions.HTTPBadRequest`
        If a parameter is requested that does not exist and no default was
        provided

    """
    try:
        arg = request.params[name]
    except KeyError:
        if default is NO_ARG:
            raise HTTPBadRequest('Missing argument %s' % name)
        else:
            return default
    try:
        if not type or type is unicode:
            return arg
        elif type is str:
            return arg.encode("utf8")
        elif type is list or type is dict:
            data = json.loads(arg)
            assert isinstance(data, type)
            return data
        elif type is datetime.datetime:
            return datetime.datetime.fromtimestamp(float(arg))
        elif type is bool:
            return arg.lower() == 'true'
        elif hasattr(type, '__from_arg__'):
            return type.__from_arg__(arg)
        else:
            return type(arg)
    except:
        raise HTTPBadRequest('Badly formatted parameter "%s"' % name)

def _post(config, uri, **kwargs):
    """
    Convenience method for making secure, admin-privileged requests to Steward
    from the config object.

    Parameters
    ----------
    uri : str
        The uri path to use
    kwargs : dict
        The parameters to pass up in the request

    """
    if not uri.startswith('/'):
        uri = '/' + uri
    local_addr = config.get_settings()['steward.address']
    cookies = kwargs.get('cookies', {})
    cookies['__token'] = config.registry.secret_auth_token
    kwargs['cookies'] = cookies
    return requests.post(local_addr + uri, **kwargs)

def _subreq(request, route_name, **kwargs):
    """
    Convenience method for doing internal subrequests

    Parameters
    ----------
    route_name : str
        The route name for the endpoint to hit
    **kwargs : dict
        The parameters to pass through in the request

    """
    req = Request.blank(request.route_path(route_name))
    req.method = 'POST'
    for key, value in kwargs.items():
        if type(value) not in (int, float, bool, str, unicode):
            kwargs[key] = pyramid.renderers.render('json', value,
                                                   request=request)
    req.body = urlencode(kwargs)
    req.cookies = request.cookies
    response = request.invoke_subrequest(req)
    if response.body:
        return json.loads(response.body)

def _run_in_bg(command, *args, **kwargs):
    """Run a command and log any exceptions"""
    try:
        command(*args, **kwargs)
    except:
        LOG.exception("Error while running in the background!")

def _run_background_task(request, command, *args, **kwargs):
    """
    Run an asynchronous command in the background

    Use this when you want to start a command in a non-blocking way and do
    not care about the return value.

    Parameters
    ----------
    command : callable
        The function to call
    args : list
        The arguments to pass to the function
    kwargs : dict
        The keyword arguments to pass to the function

    """
    thread = threading.Thread(target=lambda:_run_in_bg(command, *args,
                                                       **kwargs))
    thread.daemon = True
    thread.start()

def includeme(config):
    """ Configure the app """
    config.add_directive('post', _post)
    config.include('steward.auth')
    config.include('steward.locks')
    config.include('steward.events')
    config.include('steward.tasks')
    config.include('steward.base')
    config.add_acl_from_settings('steward')
    config.add_request_method(_param, name='param')
    config.add_request_method(_subreq, name='subreq')
    config.add_request_method(_run_background_task, name='background_task')

    config.add_route('auth', '/auth')
    config.add_view('steward.views.do_auth', route_name='auth',
                    renderer='json', permission=NO_PERMISSION_REQUIRED)
    config.add_view('steward.views.bad_request', context=HTTPBadRequest,
            renderer='json', permission=NO_PERMISSION_REQUIRED)
    config.add_view('steward.views.server_error', context=Exception,
            renderer='json', permission=NO_PERMISSION_REQUIRED)

def main(global_config, **settings):
    """ This function returns a WSGI application.

    It is usually called by the PasteDeploy framework during
    ``paster serve``.
    """
    settings = dict(settings)

    config = Configurator(settings=settings)

    return config.make_wsgi_app()
