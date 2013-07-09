""" Steward bus for publishing/subscribing to events """
import re

import logging
from pyramid.security import has_permission
from steward.auth import Root


LOG = logging.getLogger(__name__)

def publish(request):
    """ Publish an event """
    name = request.param('name')
    data = request.param('data', {}, type=dict)
    LOG.info("Publishing event %s: %s", name, data)
    for handler in request.registry.event_handlers:
        pattern = handler['pattern']
        callback = handler['callback']
        match = pattern.match(name)
        if match and has_permission(handler['permission'], Root, request):
            try:
                if pattern.groups:
                    retval = callback(request, data, *match.groups())
                else:
                    retval = callback(request, data)
                if retval is True:
                    LOG.info("Sending event %s has been blocked by "
                        "event handler %s", name, callback.__name__)
                    return
            except:
                LOG.exception("Error running event handler!")
    return request.response

def event_handlers(request):
    """ Return a list of all event handlers """
    handlers = []
    for handler in request.registry.event_handlers:
        handlers.append({'pattern':handler['pattern'].pattern,
                         'name':handler['callback'].__name__})
    return handlers

def do_event_handlers(client):
    """ Print all event handlers """
    response = client.cmd('event_handlers').json()
    longest = max([len(handler['pattern']) for handler in response])
    for handler in response:
        print '{}: {}'.format(handler['pattern'].ljust(longest),
                              handler['name'])

def pub(client, name, **kw):
    """
    Publish an event, optionally with some data

    Parameters
    ----------
    name : str
        The name of the event
    kw : dict
        The data payload for the event

    """
    client.cmd('pub', name=name, data=kw)

def _add_event_handler(config, pattern, callback, priority=100,
                       permission='default'):
    """
    Add an event handler to Steward

    Parameters
    ----------
    pattern : str
        If an event name matches this pattern, the handler will be triggered
    callback : callable
        The callback for the handler. Should take the request and event payload
        as arguments. If `pattern` contains match groups, those will be passed
        in as arguments as well.
    priority : int, optional
        Determines the order in which the event handlers are called. Higher
        priority is called first.
    permission : str, optional
        The permission required by the event publisher to run this event
        handler (default 'default')

    """
    index = 0
    regex = re.compile('^' + pattern)
    while index < len(config.registry.event_handlers):
        h_priority = config.registry.event_handlers[index]['priority']
        if priority < h_priority:
            break
        index += 1
    config.registry.event_handlers.insert(index, {'pattern':regex,
        'callback':callback, 'priority':priority, 'permission':permission})

def include_client(client):
    """ Add event commands to client """
    client.set_cmd('pub', pub)
    client.set_cmd('event_handlers', do_event_handlers)

def includeme(config):
    """ Configure the app """
    config.registry.event_handlers = []
    config.add_directive('add_event_handler', _add_event_handler)

    config.add_route('pub', '/pub')
    config.add_route('event_handlers', '/event_handlers')
    config.add_view(publish, route_name='pub')
    config.add_view(event_handlers, route_name='event_handlers', renderer='json')
