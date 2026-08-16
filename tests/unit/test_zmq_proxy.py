import socket
import threading
import time

import zmq

from aerpawlib._internal.zmq import (
    ZMQ_TYPE_ACK,
    ZMQ_TYPE_FIELD_CALLBACK,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_GOODBYE,
    ZMQ_TYPE_HELLO,
    ZMQ_TYPE_TRANSITION,
    check_zmq_proxy_reachable,
    decode_message,
    encode_message,
    run_zmq_proxy,
)


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _start_proxy() -> tuple[int, int]:
    in_port = get_free_port()
    out_port = get_free_port()
    t = threading.Thread(target=run_zmq_proxy, args=(in_port, out_port), daemon=True)
    t.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if check_zmq_proxy_reachable("127.0.0.1", timeout_s=0.05, in_port=in_port, out_port=out_port):
            return in_port, out_port
        time.sleep(0.01)
    raise RuntimeError("ZMQ proxy did not become reachable")


def _connect_pub_sub(in_port: int, out_port: int) -> tuple[zmq.Context, zmq.Socket, zmq.Socket]:
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    pub.connect(f"tcp://127.0.0.1:{in_port}")
    sub.connect(f"tcp://127.0.0.1:{out_port}")
    # Monitor-equivalent settle is the production race; this file only
    # asserts the proxy forwards JSON frames, so wait for the sockets.
    deadline = time.monotonic() + 1.0
    probe = {"msg_type": ZMQ_TYPE_HELLO, "from": "probe"}
    while time.monotonic() < deadline:
        pub.send(encode_message(probe))
        if sub.poll(timeout=50):
            decode_message(sub.recv())
            break
    return ctx, pub, sub


def test_zmq_proxy_logging(caplog):
    caplog.set_level("INFO")
    in_port, out_port = _start_proxy()
    ctx, pub, sub = _connect_pub_sub(in_port, out_port)

    transition_msg = {
        "msg_type": ZMQ_TYPE_TRANSITION,
        "from": "test_sender",
        "identifier": "test_recipient",
        "next_state": "test_state",
    }
    pub.send(encode_message(transition_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == transition_msg

    field_request_msg = {
        "msg_type": ZMQ_TYPE_FIELD_REQUEST,
        "from": "test_sender",
        "identifier": "test_recipient",
        "field": "test_field",
    }
    pub.send(encode_message(field_request_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == field_request_msg

    hello_msg = {
        "msg_type": ZMQ_TYPE_HELLO,
        "from": "test_sender",
    }
    pub.send(encode_message(hello_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == hello_msg

    goodbye_msg = {
        "msg_type": ZMQ_TYPE_GOODBYE,
        "from": "test_sender",
    }
    pub.send(encode_message(goodbye_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == goodbye_msg

    field_callback_msg = {
        "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
        "from": "test_sender",
        "identifier": "test_recipient",
        "field": "test_field",
        "value": 42,
    }
    pub.send(encode_message(field_callback_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == field_callback_msg

    ack_msg = {
        "msg_type": ZMQ_TYPE_ACK,
        "from": "test_recipient",
        "identifier": "test_sender",
        "req_id": "abc",
    }
    pub.send(encode_message(ack_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == ack_msg

    pub.close()
    sub.close()
    ctx.term()

    time.sleep(0.2)
    log_text = caplog.text
    assert "ZMQ proxy ready for runner coordination" in log_text
    assert "Forwarded state_transition test_sender -> test_recipient: next_state='test_state'" in log_text
    assert "Forwarded field_request test_sender -> test_recipient: field='test_field'" in log_text
    assert "Forwarded field_callback test_sender -> test_recipient: field='test_field', value=42" in log_text
    assert "Forwarded hello client connected: name='test_sender'" in log_text
    assert "Forwarded goodbye client disconnected: name='test_sender'" in log_text


def test_zmq_proxy_invalid_message(caplog):
    caplog.set_level("INFO")
    in_port, out_port = _start_proxy()
    ctx, pub, sub = _connect_pub_sub(in_port, out_port)

    bad_msg = {
        "msg_type": "some_invalid_type",
        "from": "test_sender",
    }
    pub.send(encode_message(bad_msg))
    assert sub.poll(timeout=1000)
    assert decode_message(sub.recv()) == bad_msg

    pub.close()
    sub.close()
    ctx.term()

    time.sleep(0.2)
    assert "Forwarded unrecognized runner message" in caplog.text


def test_check_zmq_proxy_reachable_requires_both_ports():
    in_port, out_port = _start_proxy()
    assert check_zmq_proxy_reachable("127.0.0.1", in_port=in_port, out_port=out_port)
    unused = get_free_port()
    assert not check_zmq_proxy_reachable("127.0.0.1", in_port=unused, out_port=out_port)
    assert not check_zmq_proxy_reachable("127.0.0.1", in_port=in_port, out_port=unused)
