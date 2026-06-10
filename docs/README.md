Welcome to the documentation for `aerpawlib`. This library provides a high-level Python interface for interacting with autonomous vehicles and wireless nodes within the [AERPAW (Aerial Experimentation and Research Platform for Advanced Wireless)](https://aerpaw.org) testbed.

## Overview

The `aerpawlib` framework simplifies the process of writing experiment scripts for drones and rovers. It abstracts away the complex underlying communications (such as MAVLink), allowing researchers to focus entirely on their specific mobility and networking experiments rather than low-level vehicle control.

There are two versions of the API: v1 and v2. 

The [original aerpawlib](https://github.com/morzack/aerpawlib-vehicle-control) was built on DroneKit and pymavlink. As DroneKit has not been maintained in years, the primary goal of this project is to move it to MAVSDK (the preferred framework).

There are two versions: v1 and v2.

Version 1 contains the exact same API as the original aerpawlib and fully-featured API.  Version 2 is a newer, beta API design focused on simplifying the API and improving performance. It is not yet completely ready for production but works for most use cases. 

Both versions offer robust APIs for controlling your vehicles over ArduPilot.

## Documentation Index

| Module          | Description                           |
|-----------------|---------------------------------------|
| `aerpawlib.v1`  | v1 API reference (full)               |
| `aerpawlib.v2`  | v2 API reference (beta)               |
| `aerpawlib.cli` | CLI usage guide and command reference |
