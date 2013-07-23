""" A server orchestration framework written as a Pyramid app """
import datetime
import json
import logging
from multiprocessing.pool import ThreadPool
from urllib import urlencode

import requests
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest, exception_response
from pyramid.renderers import JSON, render
from pyramid.request import Request
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.settings import asbool

from . import locks


lock = locks.lock # pylint: disable=C0103

LOG = logging.getLogger(__name__)


json_renderer = JSON() # pylint: disable=C0103
def datetime_adapter(obj, request):
    """ Convert a datetime into a unix timestamp """
    return float(obj.strftime('%s.%f'))
json_renderer.add_adapter(datetime.datetime, datetime_adapter)

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
            return asbool(arg)
        else:
            return type(arg)
    except:
        raise HTTPBadRequest('Badly formatted parameter "%s"' % name)

def _argify_kwargs(request, kwargs):
    """ Serialize keyword arguments for making an internal request """
    for key, value in kwargs.items():
        if type(value) not in (int, float, bool, str, unicode):
            kwargs[key] = render('json', value, request=request)
    return kwargs

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
    kwargs = _argify_kwargs(request, kwargs)
    req.body = urlencode(kwargs)
    req.cookies = request.cookies
    response = request.invoke_subrequest(req)
    if response.body:
        return json.loads(response.body)

def _bg_req(request, route_name, **kwargs):
    """
    Convenience method for doing internal subrequests

    Parameters
    ----------
    route_name : str
        The route name for the endpoint to hit
    cookies : dict
        The cookie dict
    **kwargs : dict
        The parameters to pass through in the request

    """
    uri = request.route_path(route_name)
    local_addr = request.registry.settings['steward.address']
    kwargs = _argify_kwargs(request, kwargs)
    # We have to convert these into a dict because after the request ends the
    # cookies are no longer accessible
    cookies = dict(request.cookies)
    def do_bg_req():
        """ Do a request in the background and raise any exceptions """
        response = requests.post(local_addr + uri, cookies=cookies, data=kwargs)
        if not response.status_code == 200:
            try:
                data = response.json()
            except:
                data = None
            kw = {}
            if data is not None:
                kw['detail'] = data['detail']
            LOG.error("Error doing request '%s' in background", uri)
            raise exception_response(response.status_code, **kw)
    request.background_task(do_bg_req)

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
    request.threadpool.apply_async(_run_in_bg, args=(command,) + args,
                                   kwds=kwargs)

def _threadpool(request):
    """ Create or retrieve a threadpool """
    if not hasattr(request.registry, 'threadpool'):
        request.registry.threadpool = ThreadPool(5)
    return request.registry.threadpool

def includeme(config):
    """ Configure the app """
    config.include('steward.auth')
    config.include('steward.locks')
    config.include('steward.events')
    config.include('steward.base')
    config.add_acl_from_settings('steward')
    config.add_request_method(_param, name='param')
    config.add_request_method(_subreq, name='subreq')
    config.add_request_method(_bg_req, name='bg_request')
    config.add_request_method(_threadpool, name='threadpool', reify=True)
    config.add_request_method(_run_background_task, name='background_task')
    config.add_renderer('json', json_renderer)


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
