"""
.. module:: test_clients
   :synopsis: Test the client-server interface

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Test the client-server interface

"""
import threading
from multiprocessing import Queue, queues
from mock import MagicMock
from tornado import gen
from datetime import timedelta
from steward import client
from steward.util import public
from . import util

class ServerMods(object):
    """Test server extension module"""
    @public
    def ping(self, server, callback=None):
        """Simple server call"""
        callback('pong')

class TestClients(util.IntegrationTest):
    """Test the client-server interface"""
    timeout = 1
    @classmethod
    def setUpClass(cls):
        super(TestClients, cls).setUpClass()
        cls.config['extension_mods'].append(ServerMods())

    @gen.engine
    def _sync_client_call(self, cmd, *args, **kwargs):
        """
        Make a call in the background with the synchronous client

        Parameters are the same as :py:meth:`steward.client.Client.cmd`

        Notes
        -----
        In order to not block the tornado ioloop, we have to run the
        synchronous client commands in a separate thread. This method handles
        all of the plumbing related to that.

        """
        callback = kwargs.pop('callback')
        cl = kwargs.pop('client', None)
        if cl is None:
            cl = client.Client(self.config)
        queue = Queue()
        def _threaded_call():
            """Make a call with the client and put the result in a queue"""
            result = cl.cmd(cmd, *args, **kwargs)
            cl.close()
            queue.put(result)

        thread = threading.Thread(target=_threaded_call)
        thread.daemon = True
        thread.start()
        self._wait_for_queue(queue, callback=callback)

    @gen.engine
    def _wait_for_queue(self, queue, timeout=1, callback=None):
        """
        Poll a queue asynchronously for a new value

        Parameters
        ----------
        queue : :py:class:`threading.Queue`
            The queue to poll from
        timeout : int, optional
            How long to wait before raising an exception (default 1)

        """
        for _ in xrange(timeout * 10):
            self.io_loop.add_timeout(timedelta(seconds=0.1),
                (yield gen.Callback('sleep')))
            yield gen.Wait('sleep')
            try:
                callback(queue.get(False))
                return
            except queues.Empty:
                pass
        raise AssertionError("Queue never sent a value!")

    def _subscribe(self, cl, event, event_callback, callback=None):
        """
        Subscribe a client to an event

        Notes
        -----
        The subscription takes a short time to 'register' with PyZMQ, so we
        have to sleep for a short amount of time after doing the subscription

        """
        cl.sub(event, event_callback)
        self.io_loop.add_timeout(timedelta(seconds=0.01), callback)

    def test_client_call_server(self):
        """Synchronous client should be able to call server extensions"""
        result = yield gen.Task(self._sync_client_call, 'ping')
        self.assert_result_equal(result, 'pong')
        self.stop()
    
    def test_client_sub_event(self):
        """Synchronous client should receive subbed events"""
        cl = client.Client(self.config)
        queue = Queue()
        yield gen.Task(self._subscribe, cl, 'test_event',
            lambda *args: queue.put(args))
        self.server.publish('test_event', 'trigger')
        result, _ = yield gen.Task(self._wait_for_queue, queue)
        self.assertEqual(result, 'test_event')

        self.stop()

    def test_client_unsub_event(self):
        """After unsubscribing, synchronous client should not receive events"""
        cl = client.Client(self.config)
        queue = Queue()
        mock = MagicMock()
        yield gen.Task(self._subscribe, cl, 'test_event1', mock)
        yield gen.Task(self._subscribe, cl, 'test_event2',
            lambda *args: queue.put(args))
        cl.unsub('test_event1')
        self.server.publish('test_event1', 'trigger')
        self.server.publish('test_event2', 'trigger')
        result, _ = yield gen.Task(self._wait_for_queue, queue)
        self.assertEqual(result, 'test_event2')
        self.assertFalse(mock.called)
        self.stop()

    def test_async_client_call_server(self):
        """Asynchronous client should be able to call server extensions"""
        cl = client.AsyncClient(self.config)
        result = yield gen.Task(cl.cmd, 'ping')
        self.assert_result_equal(result, 'pong')

        self.stop()

    def test_async_client_sub_event(self):
        """Asynchronous client should receive subbed events"""
        cl = client.AsyncClient(self.config)
        callback = yield gen.Callback('event')
        yield gen.Task(self._subscribe, cl, 'test_event', callback)
        self.server.publish('test_event', 'trigger')
        result, _ = yield gen.Wait('event')
        self.assertEqual(result, ('test_event', 'trigger'))

        self.stop()

    def test_async_client_unsub_event(self):
        """After unsubscribing, asynchronous client should not receive events"""
        cl = client.AsyncClient(self.config)
        mock = MagicMock()
        callback = yield gen.Callback('event2')
        yield gen.Task(self._subscribe, cl, 'test_event1', mock)
        yield gen.Task(self._subscribe, cl, 'test_event2', callback)
        cl.unsub('test_event1')
        self.server.publish('test_event1', 'trigger')
        self.server.publish('test_event2', 'trigger')
        result, _ = yield gen.Wait('event2')
        self.assertEqual(result, ('test_event2', 'trigger'))
        self.assertFalse(mock.called)

        self.stop()
