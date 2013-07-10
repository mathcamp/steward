""" Authentication and authorization tools for Steward """
from pyramid.authentication import AuthTktAuthenticationPolicy
from base64 import b64encode
from uuid import uuid4
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import (Allow, Deny, Everyone, Authenticated,
                              ALL_PERMISSIONS, unauthenticated_userid)
from pyramid.settings import aslist, asbool

def asint(setting):
    """ Convert variable to int, leave None unchanged """
    if setting is None:
        return setting
    else:
        return int(setting)


class Root(dict):
    """ Root context for Steward """
    __name__ = __parent__ = None
    __acl__ = [
        (Allow, 'admin', ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]

class InternalAdminAuthPolicy(object):
    """
    Specialized auth policy for internal requests

    This allows us to make calls to Steward, from Steward with admin privileges

    """
    def __init__(self, token):
        self._token = token

    def authenticated_userid(self, request):
        """ Return the authenticated userid or ``None`` if no
        authenticated userid can be found. This method of the policy
        should ensure that a record exists in whatever persistent store is
        used related to the user (the user should not have been deleted);
        if a record associated with the current id does not exist in a
        persistent store, it should return ``None``."""
        if request.cookies.get('__token', None) == self._token:
            return 'admin'

    def unauthenticated_userid(self, request):
        """ Return the *unauthenticated* userid.  This method performs the
        same duty as ``authenticated_userid`` but is permitted to return the
        userid based only on data present in the request; it needn't (and
        shouldn't) check any persistent store to ensure that the user record
        related to the request userid exists."""
        if request.cookies.get('__token', None) == self._token:
            return 'admin'

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as
        ``pyramid.security.Everyone`` and
        ``pyramid.security.Authenticated``. """
        if request.cookies.get('__token', None) == self._token:
            return ['admin']
        return []

    def remember(self, request, principal, **kw):
        """ Return a set of headers suitable for 'remembering' the
        principal named ``principal`` when set in a response.  An
        individual authentication policy and its consumers can decide
        on the composition and meaning of **kw. """
        return []

    def forget(self, request):
        """ Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests. """
        return []

class MixedAuthenticationPolicy(object):
    """
    Auth policy that is backed by multiple other auth policies

    Checks authentication against each contained policy in order. The first one
    to return a non-None result is used.

    """
    def __init__(self, *policies):
        self._policies = list(policies)

    def add_policy(self, policy):
        """ Add another authentication policy """
        self._policies.append(policy)

    def authenticated_userid(self, request):
        """ Return the authenticated userid or ``None`` if no
        authenticated userid can be found. This method of the policy
        should ensure that a record exists in whatever persistent store is
        used related to the user (the user should not have been deleted);
        if a record associated with the current id does not exist in a
        persistent store, it should return ``None``."""
        for policy in self._policies:
            userid = policy.authenticated_userid(request)
            if userid is not None:
                return userid

    def unauthenticated_userid(self, request):
        """ Return the *unauthenticated* userid.  This method performs the
        same duty as ``authenticated_userid`` but is permitted to return the
        userid based only on data present in the request; it needn't (and
        shouldn't) check any persistent store to ensure that the user record
        related to the request userid exists."""
        for policy in self._policies:
            userid = policy.unauthenticated_userid(request)
            if userid is not None:
                return userid

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as
        ``pyramid.security.Everyone`` and
        ``pyramid.security.Authenticated``. """
        principals = set()
        for policy in self._policies:
            principals.update(policy.effective_principals(request))
        return list(principals)

    def remember(self, request, principal, **kw):
        """ Return a set of headers suitable for 'remembering' the
        principal named ``principal`` when set in a response.  An
        individual authentication policy and its consumers can decide
        on the composition and meaning of **kw. """
        headers = []
        for policy in self._policies:
            headers.extend(policy.remember(request, principal, **kw))
        return headers

    def forget(self, request):
        """ Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests. """
        headers = []
        for policy in self._policies:
            headers.extend(policy.forget(request))
        return headers


class IAuthDB(object):
    """
    Interface for accessing a list of user credentials and user security groups

    """
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

    """
    def __init__(self, settings):
        self.settings = settings

    def authenticate(self, request, userid, password):
        key = 'steward.auth.{}.pass'.format(userid)
        return self.settings.get(key) == password

    def groups(self, userid, request):
        key = 'steward.auth.{}.groups'.format(userid)
        return aslist(request.registry.settings.get(key))

class YamlAuthDB(IAuthDB):
    """
    Auth object that pulls user data from a yaml file

    Parameters
    ----------
    filename : str
        Name of the yaml file with the user data

    """
    def __init__(self, filename):
        import yaml
        with open(filename, 'r') as infile:
            self.data = yaml.load(infile)

    def authenticate(self, request, userid, password):
        return self.data['users'][userid] == password

    def groups(self, user, request):
        return self.data['groups'].get(user)

def _add_authentication_policy(config, policy):
    """ Config directive that adds another auth policy to Steward """
    config.registry.authentication_policy.add_policy(policy)

def _add_acl_from_settings(config, prefix):
    """
    Load ACL data from settings

    Parameters
    ----------
    prefix : str
        The prefix of the ACL settings

    Notes
    -----
    The settings should be in the form: <prefix>.<perm>.<permission> = <list of groups>

    For example::

        myext.perm.write = developer manager

    This will give any users in the ``developer`` or ``manager`` group access
    to endpoints with the 'write' permission.


    """
    settings = config.get_settings()
    for key, value in settings.iteritems():
        if not key.startswith(prefix):
            continue
        tail = key[len(prefix):]
        if tail.startswith('.'):
            tail = tail[1:]
        components = tail.split('.')
        if len(components) != 2 or components[0] != 'perm':
            continue
        permission = components[1]
        for principle in aslist(value):
            if principle.lower() == 'authenticated':
                principle = Authenticated
            elif principle.lower() == 'everyone':
                principle = Everyone
            Root.__acl__.insert(0, (Allow, principle, permission))

def includeme(config):
    """ Configure the app """
    settings = config.get_settings()
    config.set_root_factory(Root)
    config.registry.secret_auth_token = b64encode(uuid4().bytes + uuid4().bytes)
    config.add_directive('add_acl_from_settings', _add_acl_from_settings)
    config.add_directive('add_authentication_policy',
                         _add_authentication_policy)

    if not asbool(settings.get('steward.auth.enable')):
        config.registry.auth_db = DummyAuthDB()
        return

    auth_db_source = settings.get('steward.auth.db')
    if auth_db_source is None:
        auth_db = SettingsAuthDB(settings)
    elif auth_db_source.endswith('.yaml'):
        auth_db = YamlAuthDB(auth_db_source)
    else:
        raise ValueError("Unrecognized auth database {}".format(auth_db))

    config.registry.auth_db = auth_db

    config.set_authorization_policy(ACLAuthorizationPolicy())
    config.registry.authentication_policy = MixedAuthenticationPolicy()
    config.set_authentication_policy(config.registry.authentication_policy)
    auth_policy = AuthTktAuthenticationPolicy(
        settings['pyramid.cookie.secret'],
        callback=auth_db.groups,
        cookie_name=settings.get('pyramid.cookie.name', 'auth_tkt'),
        secure=asbool(settings.get('pyramid.cookie.secure')),
        timeout=asint(settings.get('pyramid.cookie.timeout')),
        reissue_time=asint(settings.get('pyramid.cookie.reissue_time')),
        max_age=asint(settings.get('pyramid.cookie.max_age')),
        path=settings.get('pyramid.cookie.path', '/'),
        http_only=asbool(settings.get('pyramid.cookie.httponly', True)),
        wild_domain=asbool(settings.get('pyramid.cookie.wild_domain', True)),
        hashalg=settings.get('pyramid.cookie.hashalg', 'sha512'),
        debug=asbool(settings.get('pyramid.cookie.debug', False)),
    )
    config.add_authentication_policy(auth_policy)
    config.add_authentication_policy(InternalAdminAuthPolicy(
        config.registry.secret_auth_token))
    config.set_default_permission('default')

    config.add_request_method(unauthenticated_userid, name='userid', reify=True)
