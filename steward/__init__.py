""" A server orchestration framework written as a Pyramid app """
import datetime

import functools
import inspect
import json
import logging
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.interfaces import IRequest
from pyramid.renderers import JSON, render
from pyramid.request import Request
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.settings import asbool
from urllib import urlencode
from zope.interface.exceptions import DoesNotImplement
from zope.interface.verify import verifyObject


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
        elif type is datetime.datetime or type is datetime:
            return datetime.datetime.fromtimestamp(float(arg))
        elif type is bool:
            return asbool(arg)
        else:
            return type(arg)
    except:
        raise HTTPBadRequest('Badly formatted parameter "%s"' % name)


def argify(*args, **type_kwargs):
    """
    Request decorator for automagically passing in request parameters

    Notes
    -----
    Here is a sample use case::

        @argify(foo=dict, ts=datetime)
        def handle_request(request, foo, ts, bar='baz'):
            # do request handling

    No special type is required for strings::

        @argify
        def handle_request(request, foo, bar='baz'):
            # do request handling (both 'foo' and 'bar' are strings)

    If any positional arguments are missing, it will raise a HTTPBadRequest
    exception. If any keyword arguments are missing, it will simply use
    whatever the default value is.

    Note that unit tests should be unaffected by this decorator. This should be
    valid::

        @argify
        def myrequest(request, var1, var2='foo'):
            return 'bar'

        class TestReq(unittest.TestCase):
            def test_my_request(self):
                request = pyramid.testing.DummyRequest()
                retval = myrequest(request, 5, var2='foobar')
                self.assertEqual(retval, 'bar')

    """
    def wrapper(fxn):
        """ Function decorator """
        argspec = inspect.getargspec(fxn)
        if argspec.defaults is not None:
            required = argspec.args[:-len(argspec.defaults)]
            optional = argspec.args[-len(argspec.defaults):]
        else:
            required = argspec.args
            optional = ()

        for type_arg in type_kwargs:
            if type_arg not in required and type_arg not in optional:
                raise TypeError("Argument '%s' specified in argify, but not "
                                "present in function definition" % type_arg)

        def is_request(obj):
            """ Check if an object looks like a request """
            try:
                return verifyObject(IRequest, obj)
            except DoesNotImplement:
                return False

        @functools.wraps(fxn)
        def param_twiddler(*args, **kwargs):
            """ The actual wrapper function that pulls out the params """
            # If the second arg is the request, this is called from pyramid
            if len(args) == 2 and len(kwargs) == 0 and is_request(args[1]):
                context, request = args
                scope = {}
                for param in required:
                    if param == 'context':
                        scope['context'] = context
                    elif param == 'request':
                        scope['request'] = request
                    else:
                        scope[param] = _param(request, param,
                                              type=type_kwargs.get(param))
                no_val = object()
                for param in optional:
                    val = _param(request, param, default=no_val,
                                 type=type_kwargs.get(param))
                    if val is not no_val:
                        scope[param] = val
                return fxn(**scope)
            else:
                # Otherwise, it's likely a unit test. Don't alter args at all.
                return fxn(*args, **kwargs)
        return param_twiddler

    if len(args) == 1 and len(type_kwargs) == 0 and inspect.isfunction(args[0]):
        # @request params
        # def fxn(request, var1, var2):
        return wrapper(args[0])
    else:
        # @request params(var1=bool, var2=list)
        # def fxn(request, var1, var2):
        return wrapper


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
