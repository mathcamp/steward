""" A server orchestration framework written as a Pyramid app """
import datetime

import json
import logging
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.renderers import JSON, render
from pyramid.request import Request
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.settings import asbool
from urllib import urlencode


LOG = logging.getLogger(__name__)
NO_ARG = object()

json_renderer = JSON()  # pylint: disable=C0103
json_renderer.add_adapter(datetime.datetime,
                          lambda obj, _: float(obj.strftime('%s.%f')))


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
    loads = True
    try:
        if request.params:
            arg = request.params[name]
        else:
            arg = request.json_body[name]
            loads = False
    except (KeyError, ValueError):
        if default is NO_ARG:
            raise HTTPBadRequest('Missing argument %s' % name)
        else:
            return default
    try:
        if type is None or type is unicode:
            return arg
        elif type is str:
            return arg.encode("utf8")
        elif type is list or type is dict:
            if loads:
                arg = json.loads(arg)
                assert isinstance(arg, type)
            return arg
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
    for name in request.registry.subrequest_methods:
        setattr(req, name, getattr(request, name))
    kwargs = _argify_kwargs(request, kwargs)
    req.body = urlencode(kwargs)
    req.cookies = request.cookies
    response = request.invoke_subrequest(req)
    if response.body:
        return json.loads(response.body)


def _safe_subreq(request, route_name, **kwargs):
    """
    Do an internal subrequest. If the route name does not exist, return None.

    """
    try:
        return _subreq(request, route_name, **kwargs)
    except KeyError:
        return None


def includeme(config):
    """ Configure the app """
    config.registry.subrequest_methods = []
    config.include('steward.auth')
    config.include('steward.base')
    config.add_request_method(_param, name='param')
    config.add_request_method(_subreq, name='subreq')
    config.add_request_method(_safe_subreq, name='safe_subreq')
    config.add_renderer('json', json_renderer)

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
