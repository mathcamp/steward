""" Steward's default endpoints """
import logging
import traceback
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.security import remember


LOG = logging.getLogger(__name__)

def do_auth(request):
    """ Authentication endpoint for clients to log in """
    userid = request.param('userid')
    password = request.param('password')
    if request.registry.auth_db.authenticate(request, userid, password):
        request.response.headers = remember(request, userid)
        return request.response
    raise HTTPBadRequest("Login failed")

def bad_request(context, request):
    """ Return 400's with a bit more context for the client """
    request.response.status_code = 400
    return {'detail': context.detail}

def server_error(context, request):
    """ Return 500's with a bit more context for the client """
    request.response.status_code = 500
    if hasattr(context, 'detail'):
        return {'detail': context.detail}
    else:
        return {'detail': traceback.format_exc(context)}
