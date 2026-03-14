import pytest

from aerpawlib.v1.safety import (
    SafetyCheckerServer,
    deserialize_msg,
    serialize_request,
)


class _FakeSocket:
    def __init__(self):
        self._recv_count = 0
        self.sent = []

    def bind(self, _addr):
        return None

    def recv(self):
        self._recv_count += 1
        if self._recv_count == 1:
            # Not valid compressed payload; deserialize_msg should fail.
            return b"not-a-zlib-payload"
        raise KeyboardInterrupt()

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        return None


class _FakeContext:
    def __init__(self, socket_obj):
        self._socket_obj = socket_obj

    def socket(self, _socket_type):
        return self._socket_obj

    def term(self):
        return None


def test_start_server_handles_malformed_request_without_crashing(monkeypatch):
    fake_socket = _FakeSocket()
    fake_context = _FakeContext(fake_socket)

    monkeypatch.setattr("aerpawlib.v1.safety.zmq.Context", lambda: fake_context)

    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    with pytest.raises(KeyboardInterrupt):
        server.start_server(14580)

    assert len(fake_socket.sent) == 1
    response = deserialize_msg(fake_socket.sent[0])
    assert response["result"] is False
    assert "Server error" in response["message"]


class _UnknownFunctionSocket:
    def __init__(self):
        self._recv_count = 0
        self.sent = []

    def bind(self, _addr):
        return None

    def recv(self):
        self._recv_count += 1
        if self._recv_count == 1:
            return serialize_request("not_implemented", [])
        raise KeyboardInterrupt()

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        return None


def test_start_server_unknown_function_request_does_not_crash(monkeypatch):
    fake_socket = _UnknownFunctionSocket()
    fake_context = _FakeContext(fake_socket)

    monkeypatch.setattr("aerpawlib.v1.safety.zmq.Context", lambda: fake_context)

    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    with pytest.raises(KeyboardInterrupt):
        server.start_server(14581)

    assert len(fake_socket.sent) == 1
    response = deserialize_msg(fake_socket.sent[0])
    assert response["result"] is False
    assert "not_implemented" in response["message"]


