=======
Steward
=======
Steward is a platform for building centralized logic into your server stack. It
is meant to provide an extremely lightweight and flexible platform on which to
build customized behavior.


Configuration
=============
TODO::

    steward.auth.enable - bool
    steward.auth.db
        <blank> - use settings
        <file.yaml> - Load from yaml file

    pyramid.cookie.secret
    pyramid.cookie.name
    pyramid.cookie.secure
    pyramid.cookie.timeout
    pyramid.cookie.reissue_time
    pyramid.cookie.max_age
    pyramid.cookie.path
    pyramid.cookie.httponly
    pyramid.cookie.wild_domain
    pyramid.cookie.hashalg
    pyramid.cookie.debug


    User credentials
        ini
            steward.auth.<user>.pass
            steward.auth.<user>.groups
        yaml
            users:
                userid: password
            groups:
                userid: groups
