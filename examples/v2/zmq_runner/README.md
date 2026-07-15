# Leader/Follower ZMQ Example (v2)

This example demonstrates coordinated multi-vehicle operation using ZMQ for
inter-vehicle communication. The leader coordinates the follower via state
transitions using the v2 API.

## Setup

1. Start ZMQ Proxy

   ```bash
   aerpawlib-run-proxy
   ```

1. Run the leader (waits 10s, then triggers follower takeoff):

   ```bash
   aerpawlib --api-version v2 \
     --script examples/v2/zmq_runner/leader.py \
     --conn udpin://127.0.0.1:14550 \
     --vehicle drone \
     --zmq-identifier leader \
     --zmq-proxy-server 127.0.0.1
   ```

1. Run the follower (waits for leader, then takes off when commanded):

   ```bash
   aerpawlib --api-version v2 \
     --script examples/v2/zmq_runner/follower.py \
     --conn udpin://127.0.0.1:14551 \
     --vehicle drone \
     --zmq-identifier follower \
     --zmq-proxy-server 127.0.0.1
   ```

> **Note:** `--zmq-identifier` and `--zmq-proxy-server` are required for ZMQ-based
> scripts. Each vehicle needs a unique identifier (e.g. `leader`, `follower`).
