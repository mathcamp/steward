""" Miscellaneous endpoints for Steward """
import datetime
from pyramid.view import view_config


@view_config(route_name='version', renderer='json')
def version(request):
    """ Get the current version of steward """
    # pylint: disable=F0401,E0611
    from steward.__version__ import __version__
    return __version__

def include_client(client):
    """ Add commands to the client """
    # Nothing here yet
    pass

def includeme(config):
    """ Configure the app """
    config.add_route('version', '/version')
    config.scan()
