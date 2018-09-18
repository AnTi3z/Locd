import os
import socketserver
import socket
import struct
import json


class IPCError(Exception):
    pass


class ConnectionClosed(IPCError):
    pass


def _read_objects(sock):
    header = sock.recv(4)
    if len(header) == 0:
        raise ConnectionClosed()
    size = struct.unpack('!i', header)[0]
    data = sock.recv(size - 4)
    if len(data) == 0:
        raise ConnectionClosed()
    return json.loads(data)


def _write_objects(sock, objects):
    data = json.dumps(objects)
    sock.sendall(struct.pack('!i', len(data) + 4))
    sock.sendall(data.encode('utf-8'))


class Client:
    def __init__(self, server_address):
        self.addr = server_address
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def connect(self):
        self.sock.connect(self.addr)

    def close(self):
        self.sock.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def send(self, objects):
        _write_objects(self.sock, objects)
        return _read_objects(self.sock)


class Server(socketserver.UnixStreamServer):
    def __init__(self, server_address, callback, bind_and_activate=True):
        self.addr = server_address

        if not callable(callback):
            callback = lambda x: []

        class IPCHandler(socketserver.BaseRequestHandler):
            def handle(self):
                while True:
                    try:
                        results = _read_objects(self.request)
                    except ConnectionClosed as e:
                        return
                    _write_objects(self.request, callback(results))

        socketserver.TCPServer.__init__(self, server_address, IPCHandler, bind_and_activate)

    def server_close(self):
        super().server_close()
        try:
            os.unlink(self.addr)
        except OSError:
            if os.path.exists(self.addr):
                raise
