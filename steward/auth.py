""" Authentication and authorization tools for Steward """
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.path import DottedNameResolver
from pyramid.security import (Allow, Deny, Everyone, Authenticated,
                              ALL_PERMISSIONS, unauthenticated_userid,
                              NO_PERMISSION_REQUIRED)
from pyramid.settings import aslist, asbool


def asint(setting):
    """ Convert variable to int, leave None unchanged """
    if setting is None:
        return setting
    else:
        return int(setting)


class Root(object):

    """ Root context for Steward """
    __name__ = __parent__ = None
    __acl__ = [
        (Allow, 'admin', ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]
    def __init__(self, request):
        self.request = request


class IAuthDB(object):

    """
    Interface for accessing a list of user credentials and user security groups

    """
    def __init__(self, config):
        self.config = config

    def authenticate(self, request, userid, password):
        """
        Check a user's login credentials

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
            The active request object
        userid : str
            The userid of the user logging in
        password : str
            The password provided by the user logging in

        Returns
        -------
        valid : bool

        """
        raise NotImplementedError

    def groups(self, userid, request):
        """
        Get this list of groups the user belongs to (security principals)

        Parameters
        ----------
        userid : str
            userid to get groups for
        request : :class:`pyramid.request.Request`
            The active request object

        """
        raise NotImplementedError


class DummyAuthDB(IAuthDB):

    """
    Auth object that allows anyone to log in as anything, but has no security
    principals

    """
    def authenticate(self, request, userid, password):
        return True

    def groups(self, userid, request):
        return []


class SettingsAuthDB(IAuthDB):

    """
    Auth object that pulls user data out of the app settings

    Parameters
    ----------
    settings : dict
        The settings for the pyramid app

    Notes
    -----
    The format of the config file is::

        steward.auth.<username>.pass = <salted password>
        steward.auth.<username>.groups = <list of groups>

    """
    def authenticate(self, request, userid, password):
        key = 'steward.auth.{0}.pass'.format(userid)
        stored_pw = self.config.get_settings().get(key)
        if stored_pw is None:
            return False
        return sha256_crypt.verify(password, stored_pw)

    def groups(self, userid, request):
        key = 'steward.auth.{0}.groups'.format(userid)
        return aslist(request.registry.settings.get(key, []))


class YamlAuthDB(IAuthDB):

    """
    Auth object that pulls user data from a yaml file

    Parameters
    ----------
    filename : str
        Name of the yaml file with the user data

    Notes
    -----
    The format of the yaml file is::

        users:
            <username>: <salted password>
        groups:
            <username>:
                - <group1>
                - <group2>

    You may either put the path to the yaml file in the field
    ``steward.auth.db.file`` or as the value of ``steward.auth.db`` directly

    """
    def __init__(self, config):
        super(YamlAuthDB, self).__init__(config)
        import yaml
        settings = config.get_settings()
        filename = settings.get('steward.auth.db.file',
                                settings['steward.auth.db'])
        with open(filename, 'r') as infile:
            self.data = yaml.safe_load(infile)

    def authenticate(self, request, userid, password):
        stored_pw = self.data['users'].get(userid)
        if stored_pw is None:
            return False
        return sha256_crypt.verify(password, stored_pw)

    def groups(self, user, request):
        return self.data['groups'].get(user)


def add_acl_from_settings(config):
    """
    Load ACL data from settings

    Notes
    -----
    The settings should be in the form::

        steward.perm.<permission> = <list of groups>

    For example::

        steward.perm.schedule_write = developer manager

    This will give any users in the ``developer`` or ``manager`` group access
    to endpoints with the 'schedule_write' permission.


    """
    settings = config.get_settings()
    for key, value in settings.iteritems():
        if not key.startswith('steward.perm.'):
            continue
        permission = key.split('.')[2]
        for principle in aslist(value):
            if principle.lower() == 'authenticated':
                principle = Authenticated
            elif principle.lower() == 'everyone':
                principle = Everyone
            Root.__acl__.insert(0, (Allow, principle, permission))


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()
    name_resolver = DottedNameResolver(__package__)
    config.set_root_factory(Root)
    add_acl_from_settings(config)

    config.add_route('auth', '/auth')
    config.add_view('steward.views.do_auth', route_name='auth',
                    renderer='json', permission=NO_PERMISSION_REQUIRED)
    config.add_route('check_auth', '/check_auth')
    config.add_view('steward.views.do_check_auth', route_name='check_auth',
                    renderer='json', permission=NO_PERMISSION_REQUIRED)

    if not asbool(settings.get('steward.auth.enable')):
        config.registry.auth_db = DummyAuthDB(config)
        return

    auth_db_source = settings.get('steward.auth.db', 'settings')
    if auth_db_source == 'settings':
        auth_db_source = 'steward.auth.SettingsAuthDB'
    elif auth_db_source.endswith('.yaml'):
        auth_db_source = 'steward.auth.YamlAuthDB'
    auth_db = name_resolver.resolve(auth_db_source)(config)

    config.registry.auth_db = auth_db

    config.set_authentication_policy(config.registry.authentication_policy)
    config.set_authorization_policy(ACLAuthorizationPolicy())
    auth_policy = AuthTktAuthenticationPolicy(
        settings['steward.cookie.secret'],
        callback=auth_db.groups,
        cookie_name=settings.get('steward.cookie.name', 'auth_tkt'),
        secure=asbool(settings.get('steward.cookie.secure')),
        timeout=asint(settings.get('steward.cookie.timeout')),
        reissue_time=asint(settings.get('steward.cookie.reissue_time')),
        max_age=asint(settings.get('steward.cookie.max_age')),
        path=settings.get('steward.cookie.path', '/'),
        http_only=asbool(settings.get('steward.cookie.httponly', True)),
        wild_domain=asbool(settings.get('steward.cookie.wild_domain', True)),
        hashalg=settings.get('steward.cookie.hashalg', 'sha512'),
        debug=asbool(settings.get('steward.cookie.debug', False)),
    )
    config.add_authentication_policy(auth_policy)
    config.set_default_permission('default')

    config.add_request_method(unauthenticated_userid, name='userid',
                              reify=True)
