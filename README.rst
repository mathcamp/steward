=======
Steward
=======

Steward is a platform for building centralized logic into your server stack. It
is meant to provide an extremely lightweight and flexible platform on which to
build customized behavior.

Quick Start
===========

To get started, just ``pip install .`` and run ``steward-server``. To connect,
open another terminal and run ``steward``. You now have an interactive session
that can run commands! To customize the options, you can copy the steward.yaml
configuration file into /etc/, or pass in options on the command line.

Writing Extensions
==================

The real utility in Steward lies in the ability to write custom extensions.
Steward was built to be used with `salt <http://docs.saltstack.com>`_, but
there's no limit to the tools you could build in as extensions.

This is just a broad overview of how to write extensions. For more detail,
refer to the docstrings in the referenced methods.

Methods
-------

There are two basic ways to write your extensions. There's the raw way::

    from steward import public

    @public
    def do_something(self):
        my_list = ['foo', 'bar', 'baz']
        return my_list

The ``@public`` decorator will attach your method to the server object. Other
extensions and clients will be able to call it.

Often you may want to bundle up multiple commands into a common namespace. For
that, you can create a class::

    from steward import public

    @public
    class Shop(object):
        @public
        def stilton(self):
            return "Sorry"

        @public
        def brie(self):
            return "No"

        @public
        def camembert(self):
            return "It's a little runny, sir"

These methods will be accessable as ``shop.stilton``, ``shop.brie``, and
``shop.camembert``.

If you define a special method named ``on_start``, it will be run when the
server starts up.  You can use this to set up static resources on the server
object that your extensions need::

    from steward import public

    def on_start(self):
        self.orders = []

    @public
    def order(self, item):
        self.orders.append(item)
        return True

    @public
    def serve(self):
        return self.orders.pop(0)

Tasks
-----

Another construct that Steward supports in extensions is Tasks. A task is
anything that should be run periodically. The default is to use a cron-style
format, but you can write your own custom scheduler. See the docs for details::

    from steward import task

    @task('*/10 * * * *')
    def change_walk(self):
        self.silly_walk.rotate()

Events
------

The last basic construct that Steward supports is Events. An Event is a single
call that is processed by event handlers and then broadcast to all clients.
Events consist of a tag and (optionally) a payload. The base Steward code does
not send any events; all events come from extensions::

    import random
    from steward import public, event_handler

    def on_start(self):
        self.weapons = ['banana', 'raspberry', 'pineapple', 'pointed stick']

    def attack(self):
        payload = {
            'weapon':random.choice(self.weapons)
        }
        self.publish('attack', payload)
        return True

    @event_handler('attack')
    def handle_attack(self, payload):
        try:
            self.fire_gun()
        except AttributeError:
            self.drop_16_ton_weight()

You may use regular expressions in your event handler. See the documentation
for examples.

Using Extensions
----------------

To load your custom extensions, put them into some common directory (such as
/srv/steward) and add that directory to the 'extensions' option in the
steward.yaml configuration file. You can also specify it on the command line
with ``--extensions``.

Another way to load extensions is to put them in a package and install them
using pip. Then you can specify the package name in the 'pkg_extensions' option
in the steward.yaml configuration file, or on the command line with
``--pkg-extensions``.

More
----

You can find more examples at http://github.com/mathcamp/steward-extensions,
including a simple functioning salt extension. (Are you using salt? You really
should.)
