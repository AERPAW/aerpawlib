# ZMQ Preplanned Orbit (v2)

Multi-drone example: two drones (tracer + orbiter) coordinated via ZMQ. The tracer follows waypoints from a `.plan` file; the orbiter orbits the tracer at each waypoint. A ground coordinator orchestrates the mission.

> Start the ZMQ proxy first: `aerpawlib-run-proxy`

## Tracer

```bash
aerpawlib --api-version v2 --vehicle drone --conn udpin://127.0.0.1:14570 \
    --zmq-identifier tracer --zmq-proxy-server 127.0.0.1 \
    --script examples/v2/zmq_preplanned_orbit/drone_tracer.py
```

## Orbiter

```bash
aerpawlib --api-version v2 --vehicle drone --conn udpin://127.0.0.1:14580 \
    --zmq-identifier orbiter --zmq-proxy-server 127.0.0.1 \
    --script examples/v2/zmq_preplanned_orbit/drone_orbiter.py
```

## Ground Coordinator

```bash
aerpawlib --api-version v2 --vehicle none --conn udpin://127.0.0.1:14550 --skip-init \
    --zmq-identifier ground --zmq-proxy-server 127.0.0.1 \
    --script examples/v2/zmq_preplanned_orbit/ground_coordinator.py \
    --file examples/v2/zmq_preplanned_orbit/orbit.plan
```
