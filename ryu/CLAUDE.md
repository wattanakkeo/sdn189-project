# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ryu is a component-based Software Defined Networking (SDN) framework — an OpenFlow controller written in Python. It allows developers to build network management applications using event-driven APIs. Note: the project is not actively maintained; [faucetsdn/ryu](https://github.com/faucetsdn/ryu) is the current fork and [os-ken](https://opendev.org/x/os-ken) is the maintained alternative.

## Commands

### Install dependencies
```bash
pip install -r tools/pip-requires
pip install -r tools/test-requires
pip install -r tools/optional-requires  # For NETCONF, BGP, OF-Config
```

### Run tests
```bash
tox                        # Full test matrix (py35–py39, style, type checks)
tox -e py38                # Single Python version
tox -e pycodestyle         # Style check only
tox -e autopep8            # Format check only
tox -e pytype              # Type checking only
./run_tests.sh             # Legacy test runner (supports -c coverage, -p style, -l lint)
```

### Run a single test file
```bash
python -m pytest ryu/tests/unit/packet/test_packet.py
# Or via nose:
python ryu/tests/run_tests.py ryu/tests/unit/packet/test_packet.py
```

### Format code
```bash
autopep8 --recursive --in-place ryu/
```

### Run Ryu
```bash
ryu-manager ryu/app/simple_switch_13.py   # Example: run a learning switch
ryu-manager your_app.py --ofp-tcp-listen-port 6653
```

## Architecture

### Event-Driven Application Model

Applications inherit from `RyuApp` (`ryu/base/app_manager.py`) and register handlers with `@set_ev_cls(EventClass, DispatcherState)`. The `AppManager` loads apps, resolves service dependencies, and routes events between them.

**Message flow:**

```
OpenFlow Switch (TCP 6653/6633)
  → controller.py         # Connection management, dispatches to datapath
  → ofp_handler.py        # Parses raw OpenFlow messages into event objects
  → Event dispatcher      # Delivers events to @set_ev_cls handlers in RyuApp instances
```

### Key Modules

| Module | Role |
|--------|------|
| `ryu/base/app_manager.py` | `RyuApp` base class; service brick loading/wiring |
| `ryu/controller/controller.py` | TCP server; per-datapath greenlet and event pump |
| `ryu/controller/handler.py` | `@set_ev_cls` decorator; dispatcher state machine |
| `ryu/controller/dpset.py` | Tracks active switches and their features/ports |
| `ryu/ofproto/` | Per-version protocol constants + parser/serializer pairs |
| `ryu/lib/hub.py` | Thin wrapper over eventlet — all green threading goes here |
| `ryu/lib/packet/` | Packet parsing/construction (Ethernet, IP, TCP, VLAN, etc.) |
| `ryu/topology/switches.py` | LLDP-based link discovery; emits topology events |
| `ryu/app/` | Example and reference applications (simple switch, REST APIs) |
| `ryu/services/protocols/` | BGP, NETCONF, and other control-plane protocol stacks |

### OpenFlow Protocol Layout

Each supported version (1.0, 1.2, 1.3, 1.4, 1.5) has two files in `ryu/ofproto/`:
- `ofproto_v1_X.py` — constants (message types, action types, etc.)
- `ofproto_v1_X_parser.py` — `MsgBase` subclasses with `parser()`/`serialize()` methods

Version negotiation happens at handshake; the datapath object carries the selected `ofproto` and `ofproto_parser` references.

### Concurrency Model

Ryu uses **eventlet** green threads (cooperative multitasking). All blocking I/O must go through eventlet-patched equivalents. `ryu/lib/hub.py` provides `spawn()`, `sleep()`, `Queue`, etc. — use these instead of stdlib threading primitives.

### Dispatcher States

Handlers must declare which connection phase they handle:
- `HANDSHAKE_DISPATCHER` — before features reply
- `CONFIG_DISPATCHER` — after features, before flow-mod setup
- `MAIN_DISPATCHER` — normal operation

### Minimal Application Template

```python
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

class MyApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features_handler(self, ev):
        datapath = ev.msg.datapath
        # install table-miss flow, etc.

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
```

## Code Style

- PEP 8 with relaxed rules: E116, E402, E501, E722, E731, E741, W503, W504 are ignored (see `tox.ini`).
- `autopep8` is the canonical formatter; run it before committing.
- Avoid bare `except:` despite E722 being ignored.
