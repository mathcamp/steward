""" Miscellaneous endpoints for Steward """
import pkg_resources
from pyramid.settings import aslist
from pyramid.view import view_config


@view_config(route_name='version', renderer='json')
def version(request):
    """ Get the current version of steward and all extensions """
    retval = {}
    for name in aslist(request.registry.settings['pyramid.includes']):
        name = name.split('.')[0]
        retval[name] = pkg_resources.get_distribution(name).version
    return retval


def do_version(client):
    """ Get the current version of steward and all extensions """
    response = client.cmd('/version').json()
    for key, val in sorted(response.items()):
        print '%s==%s' % (key, val)


def include_client(client):
    """ Add commands to the client """
    client.set_cmd('version', do_version)


def includeme(config):
    """ Configure the app """
    config.add_route('version', '/version')
    config.scan()
