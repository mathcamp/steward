=======
Steward
=======
Steward is a platform for building centralized logic into your server stack. It
is meant to provide an extremely lightweight and flexible platform on which to
build customized behavior.

Quick Start
===========
Install steward with pip. Then run ``pserve development.ini``. Now that the
steward server is running, you should start the client with ``steward -c
client.yaml``. This will open an interactive prompt. Feel free to play around
(the ``help`` command is useful), but there won't be many options yet. For
that, you need to add extensions!

Extensions
==========
Extensions are the meat of Steward. They allow you to add essentially unlimited
functionality. Usually extensions will have instructions for how to add them in
the README, but the general idea is usually to add them to the
``pyramid.include`` section of the config file and the ``includes`` section of
the client.yaml file.

Configuration
=============
Here is a summary of all configuration options. When a value is provided, that
is the default value. If there is no default value, a placeholder will be
provided inside angle brackets::

    # Enable auth for steward
    steward.auth.enable = false
    # For each permission, provide a list of groups that can access that
    # permission. (The special keywords 'authenticated' and 'everyone' work)
    steward.perm.<permission> = <group1> <group2>
    # There is a special permission named "default" which will apply to all
    # endpoints not explicitly marked with a permission
    steward.perm.default
    # The source of user auth credentials. Should be an instance of
    # ``steward.auth.IAuthDB``. 'settings' and 'yaml' are shortcuts.
    steward.auth.db = settings

    # Steward uses pyramid's Auth Ticket Authentication Policy. It can be
    # configured with the following parameters:
    steward.cookie.secret = <cookie secret>
    steward.cookie.name = auth_tkt
    steward.cookie.secure = <bool (forces https)>
    steward.cookie.timeout = <max age of the ticket>
    steward.cookie.reissue_time = <reissue the ticket after this long>
    steward.cookie.max_age = <max age of the cookie>
    steward.cookie.path = /
    steward.cookie.httponly = true
    steward.cookie.wild_domain = true
    steward.cookie.hashalg = sha512
    steward.cookie.debug = false

Client Configuration
====================
The Steward client can specify a config file with the ``-c`` option. This
should be a yaml file. All keys are optional::

    # This is a list of all steward extensions to include. They will typically
    # add additional commands to the client.
    includes:
        - <pkg1>
        - <pkg2>
    # Any additional keyword arguments for the ``request.post`` call
    request_params: {}
    # Change the prompt
    prompt: '==> '
    # Set command aliases
    aliases:
        <alias>: <command to alias>
    # Path to the file where auth cookies are stored. Use None to disable
    # saving auth cookies.
    cookie_file: <defaults to $HOME/.steward_cookie>
