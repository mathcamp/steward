"""
.. module:: streams
   :synopsis: ZeroMQ wrappers for convenient message passing

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

ZeroMQ wrappers for convenient message passing

"""
import zlib
import zmq
import zmq.eventloop.zmqstream
import pickle
import logging
from abc import ABCMeta, abstractmethod
try:
    import simplejson as json
except ImportError:
    import json
try:
    import msgpack
except ImportError:
    pass
from . import util

LOG = logging.getLogger(__name__)

def default_stream(stream_class, socket_addr, socket_type, server,
    callback=None):
    """
    Convenience method for creating a :py:class:`~steward.streams.BaseStream`

    Parameters
    ----------
    stream_class : str
        Name of the stream class to instantiate
    socket_addr : str
        Address of the socket to connect to
    socket_type : int
        Type of socket (ex. zmq.SUB, zmq.ROUTER, zmq.REQ, etc.)
    server : bool
        If true, will bind to the socket instead of connecting
    callback : callable, optional
        See the documentation on :py:class:`~steward.streams.BaseStream`

    Returns
    -------
    stream : :py:class:`~steward.streams.BaseStream`

    Examples
    --------
    With a standard configuration dictionary named ``conf``:
        
    >>> stream = default_stream(conf['stream'], conf['server_socket'], zmq.REQ, False)

    """
    c = zmq.Context()
    socket = c.socket(socket_type)
    if server:
        socket.bind(socket_addr)
    else:
        socket.connect(socket_addr)
    return util.load_class(stream_class, 'steward.streams')(socket, callback)

class BaseStream(object):
    """
    Abstract base class for communicating over zeromq.

    Handles both synchronous and asynchronous (using tornado's ioloop) communication, though not both simultaneously. How you instantiate the stream determines if it is synchronous or asynchronous. See the Parameters section below for more information.

    Parameters
    ----------
    socket : :py:class:`zmq.Socket`
        The socket to use for communication
    callback : callable, optional
        If specified, this callback will be called with any messages received
        by the stream. If it is specified, the stream will run using tornado's
        ioloop. If unspecified, the stream will be synchronous. For information
        on the signature of the callback function, refer to the documentation
        of the :py:meth:`~steward.streams.BaseStream.recv` method below.
    
    Notes
    -----
    We have to construct the zeromq frames ourselves, since we want more
    control over the messages. You can find documentation on the frames here:
    http://zguide.zeromq.org/page:all#The-Extended-Reply-Envelope

    """
    __metaclass__ = ABCMeta
    def __init__(self, socket, callback=None):
        self._socket = socket
        self._callback = callback
        if self._callback:
            self._stream = zmq.eventloop.zmqstream.ZMQStream(socket)
            self._stream.on_recv(self._on_msg)
        else:
            self._stream = self._socket

    def _on_msg(self, message):
        """
        Asynchronous callback from ZMQStream

        Parameters
        ----------
        message : list
            The multipart representation of a zmq message

        """
        try:
            args = self._translate_msg(message)
            if isinstance(args, tuple):
                self._callback(self, *args)
            else:
                self._callback(self, args)
        except Exception as e:
            LOG.exception(e)

    def sub(self, channel):
        """
        Subscribe to a specific channel for events from the server

        Parameters
        ----------
        channel : str
            The channel to subscribe to

        Raises
        ------
        TypeError
            If the socket type is not zmq.SUB

        """
        channel = unicode(channel)
        if self._socket.socket_type != zmq.SUB:
            raise TypeError("Cannot subscribe on a non-SUB socket!")
        self._socket.setsockopt_string(zmq.SUBSCRIBE, channel)

    def unsub(self, channel):
        """
        Unsubscribe from a specific channel for events from the server

        Parameters
        ----------
        channel : str
            The channel to unsubscribe from

        Raises
        ------
        TypeError
            If the socket type is not zmq.SUB

        """
        channel = unicode(channel)
        if self._socket.socket_type != zmq.SUB:
            raise TypeError("Cannot unsubscribe on a non-SUB socket!")
        self._socket.setsockopt_string(zmq.UNSUBSCRIBE, channel)

    def _translate_msg(self, message):
        """Deserialize a zmq frame into useful objects"""
        if self._socket.socket_type in (zmq.REQ, zmq.REP, zmq.DEALER):
            obj = self.deserialize(''.join(message))
            return obj
        elif self._socket.socket_type == zmq.SUB:
            name = message[0]
            obj = self.deserialize(''.join(message[1:]))
            return name, obj
        elif self._socket.socket_type == zmq.ROUTER:
            uid = message[0]
            obj = self.deserialize(''.join(message[2:]))
            return uid, obj
        else:
            raise Exception("not implemented yet")

    @abstractmethod
    def serialize(self, obj):
        """
        Serialize an object for transport

        Parameters
        ----------
        obj : object
            The object to serialize

        Returns
        -------
        string : str
            The serialized form of the object

        """

    @abstractmethod
    def deserialize(self, message):
        """
        Deserialize a message that was received

        Parameters
        ----------
        message : str
            The message to deserialize

        Returns
        -------
        obj : object
            The deserialized form of the message

        """

    def recv(self):
        """
        Blocking call to retrieve a message

        Raises
        ------
        AttributeError
            If the stream is asynchronous

        Notes
        -----
        The return value(s) depend on the type of socket.

        REQ, REP, DEALER return the object::

            obj = stream.recv()

        SUB returns the name of the channel and an object::

            channel, obj = stream.recv()

        ROUTER returns the client uid and an object::

            client_uid, obj = stream.recv()

        """
        if self._callback is not None:
            raise AttributeError("Asynchronous stream should not call recv()!")
        msg = self._socket.recv_multipart()
        return self._translate_msg(msg)

    def send(self, *args):
        """
        Send a message on the stream.

        Notes
        -----
        The parameters for send() vary based on the type of socket

        REQ, REP, DEALER just send the object::

            stream.send(obj)

        PUB sends the name of the channel and the object::

            stream.send(channel, obj)

        ROUTER sends the uid of the client and the object::

            stream.send(client_uid, obj)

        """
        if self._socket.socket_type in (zmq.REQ, zmq.REP):
            self._stream.send(self.serialize(args[0]))
        elif self._socket.socket_type == zmq.PUB:
            self._stream.send_multipart([args[0], self.serialize(args[1])])
        elif self._socket.socket_type == zmq.ROUTER:
            self._stream.send_multipart([args[0], '', self.serialize(args[1])])
        elif self._socket.socket_type == zmq.DEALER:
            self._stream.send_multipart(['', self.serialize(args[0])])
        else:
            raise Exception("not implemented yet")

    def close(self):
        """Close the stream"""
        self._stream.close()

class PickleStream(BaseStream):
    """Stream that serializes with zlib and pickle"""
    def serialize(self, obj):
        return zlib.compress(pickle.dumps(obj))

    def deserialize(self, obj):
        return pickle.loads(zlib.decompress(obj))

class JsonStream(BaseStream):
    """Stream that serializes with zlib and json"""
    def serialize(self, obj):
        return zlib.compress(json.dumps(obj))

    def deserialize(self, obj):
        return json.loads(zlib.decompress(obj))

class MsgPackStream(BaseStream):
    """Stream that serializes with zlib and MsgPack"""
    def serialize(self, obj):
        return zlib.compress(msgpack.packb(obj))

    def deserialize(self, obj):
        return msgpack.unpackb(zlib.decompress(obj))
