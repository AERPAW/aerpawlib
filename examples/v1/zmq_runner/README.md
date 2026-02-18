# Leader/Follower ZMQ Example

This example demonstrates coordinated multi-vehicle operation using ZMQ for
inter-vehicle communication. The leader coordinates the follower via state
transitions.

## Setup

1. Start ZMQ Proxy

   ```bash
   aerpawlib --run-proxy
   ```

2. Run the leader (waits 10s, then triggers follower takeoff):

   ```bash
   aerpawlib \
     --script examples.v1.zmq_runner.leader \
     --conn udp:127.0.0.1:14550 \
     --vehicle drone \
     --zmq-identifier leader \
     --zmq-proxy-server 127.0.0.1
   ```

3. Run the follower (waits for leader, then takes off when commanded):

   ```bash
   aerpawlib \
     --script examples.v1.zmq_runner.follower \
     --conn udp:127.0.0.1:14551 \
     --vehicle drone \
     --zmq-identifier follower \
     --zmq-proxy-server 127.0.0.1
   ```

> Note: `--zmq-identifier` and `--zmq-proxy-server` are required for ZMQ-based
scripts. Each vehicle needs a unique identifier (e.g. `leader`, `follower`).
