"""
ZmqStateMachine v2 Example - Remote state transitions via ZMQ.

Run with:
    # Terminal 1: start ZMQ proxy
    aerpawlib --run-proxy

    # Terminal 2: run this script
    aerpawlib --api-version v2 --script examples/v2/zmq_state_machine_example.py \
        --vehicle drone --conn udpin://127.0.0.1:14550 \
        --zmq-identifier leader --zmq-proxy-server 127.0.0.1
"""

from aerpawlib.v2.runner import ZmqStateMachine, expose_zmq, state
from aerpawlib.v2.vehicle import Drone


class RemoteMission(ZmqStateMachine):
    """State machine with fly state exposed for remote ZMQ transition."""

    @state(name="start", first=True)
    async def start(self, drone: Drone):
        print("[example] In start state, transitioning to fly")
        return "fly"

    @state(name="fly")
    @expose_zmq("fly")
    async def fly(self, drone: Drone):
        print("[example] Flying - takeoff and hover")
        await drone.takeoff(altitude=5)
        await drone.land()
        return
