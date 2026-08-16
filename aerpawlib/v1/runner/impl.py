"""
Runner implementations for the v1 API.

This module contains the concrete Runner implementations used by the v1
interface: ``Runner`` (the abstract base), ``BasicRunner``, ``StateMachine``,
and ``ZmqStateMachine``.  The implementations here are intentionally small and
opinionated to make mission code easy to write while keeping runtime
behavior explicit and testable.
"""

from __future__ import annotations

import asyncio
import inspect
import traceback
import types
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aerpawlib._internal.zmq import (
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZmqTransport,
    check_zmq_proxy_reachable,
    decode_value,
)
from aerpawlib.v1.constants import (
    STATE_MACHINE_DELAY_S,
    ZMQ_QUERY_FIELD_TIMEOUT_S,
    ZMQ_TRANSITION_TIMEOUT_S,
    ZMQ_TYPE_FIELD_CALLBACK,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_TRANSITION,
)
from aerpawlib.v1.exceptions import (
    InvalidStateError,
    MultipleInitialStatesError,
    NoEntrypointError,
    NoInitialStateError,
    StateMachineError,
)
from aerpawlib.v1.log import LogComponent, get_logger

from .decorators import _State

if TYPE_CHECKING:
    from aerpawlib.v1.vehicle import Vehicle

logger = get_logger(LogComponent.RUNNER)

_BackgroundTask = Callable[..., Any]
_InitializationTask = Callable[..., Any]


class OrchestratedRunDescriptor:
    """Descriptor that intercepts attribute access on 'run' to return the base/parent class's
    orchestrator 'run' method instead of the user's custom method, avoiding name collisions
    while keeping the original function accessible to the orchestrator.
    """

    def __init__(self, user_run_func: Any, base_run_method: Any) -> None:
        self.user_run_func = user_run_func
        self.base_run_method = base_run_method

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return types.MethodType(self.base_run_method, obj)


class Runner:
    """Base class for experiment runners executed by the CLI.

    Subclass ``BasicRunner``, ``StateMachine``, or ``ZmqStateMachine``.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ in ("Runner", "BasicRunner", "StateMachine", "ZmqStateMachine"):
            return
        if "run" in cls.__dict__:
            user_run_func = cls.__dict__["run"]
            # If the user's run is a descriptor, retrieve the original function
            if hasattr(user_run_func, "func"):
                user_run_func = user_run_func.func
            # Find the parent/base class's 'run' method
            base_run_method = None
            for base in cls.__mro__[1:]:
                if "run" in base.__dict__:
                    base_run_method = base.__dict__["run"]
                    if isinstance(base_run_method, OrchestratedRunDescriptor):
                        continue
                    break
            if base_run_method is not None:
                cls.run = OrchestratedRunDescriptor(user_run_func, base_run_method)

    def _get_decorated_methods(self) -> list[tuple[str, Any, Any]]:
        """Returns a list of tuples (name, bound_method, raw_func) for all class methods,
        resolving any OrchestratedRunDescriptor to inspect the original decorated function.
        """
        results = []
        for name, attr in inspect.getmembers(self.__class__):
            if isinstance(attr, OrchestratedRunDescriptor):
                func = attr.user_run_func
                method = types.MethodType(func, self)
            else:
                func = attr
                method = getattr(self, name, None)
                if not inspect.ismethod(method):
                    continue
            results.append((name, method, func))
        return results

    async def run(self, vehicle: Vehicle) -> None:
        """
        Core logic of the script.

        This method is called by the launch script after initializations.
        It should be overridden by subclasses to implement specific execution models.

        Args:
            vehicle: The vehicle object initialized for this script.
        """
        pass

    def initialize_args(self, _: list[str]) -> None:
        """
        Parse and handle additional command-line arguments.

        Args:
            _: List of command-line arguments as strings.
        """
        pass

    def cleanup(self) -> None:
        """
        Perform cleanup tasks when the script exits.
        """
        pass


class BasicRunner(Runner):
    """Runner with a single ``@entrypoint`` coroutine.

    See ``aerpawlib.v1.runner`` module documentation.
    """

    def _build(self) -> None:
        """Discover and validate the single ``@entrypoint`` method."""
        self._entry = None
        for _name, method, func in self._get_decorated_methods():
            if hasattr(func, "_entrypoint"):
                if self._entry is not None:
                    raise StateMachineError(
                        "Multiple @entrypoint decorators found. BasicRunner supports exactly one entry point.",
                    )
                self._entry = method

    async def run(self, vehicle: Vehicle) -> None:
        """Execute the discovered entrypoint and then call cleanup."""
        self._build()
        if self._entry is None:
            raise NoEntrypointError()
        from aerpawlib.cli.progress_bar import update_progress

        update_progress(f"Running entrypoint: {self._entry.__name__}", completed=70)
        try:
            await self._entry.__func__(self, vehicle)
        finally:
            self.cleanup()


class StateMachine(Runner):
    """Runner that transitions between named ``@state`` methods.

    Each state returns the next state name or ``None`` to finish.
    See ``aerpawlib.v1.runner`` module documentation.
    """

    def __init__(self) -> None:
        """Initialise per-run state machine fields."""
        self._states: dict[str, _State] = {}
        self._background_tasks: list[_BackgroundTask] = []
        self._initialization_tasks: list[_InitializationTask] = []
        self._background_task_futures: list[asyncio.Future] = []
        self._entrypoint = ""
        self._current_state = ""
        self._next_state_overrides: list[str] = []
        self._running = False

    @property
    def _override_next_state_transition(self) -> bool:
        return len(self._next_state_overrides) > 0

    @_override_next_state_transition.setter
    def _override_next_state_transition(self, value: bool) -> None:
        if not value:
            if self._next_state_overrides:
                self._next_state_overrides.pop(0)

    @property
    def _next_state_overr(self) -> str:
        return self._next_state_overrides[0] if self._next_state_overrides else ""

    @_next_state_overr.setter
    def _next_state_overr(self, value: str) -> None:
        if not value:
            return
        if self._next_state_overrides:
            self._next_state_overrides[0] = value
        else:
            self._next_state_overrides.append(value)

    def _build(self) -> None:
        """
        Introspect the class to identify states, background tasks, and init tasks.

        Raises:
            MultipleInitialStatesError: If more than one state is marked 'first'.
            NoInitialStateError: If no initial state is found.
        """
        self._states = {}
        self._background_tasks = []
        self._initialization_tasks = []
        self._background_task_futures = []
        _found_initial = False
        for _name, method, func in self._get_decorated_methods():
            if hasattr(func, "_is_state"):
                self._states[func._state_name] = _State(method, func._state_name)
                if func._state_first:
                    if _found_initial:
                        raise MultipleInitialStatesError()
                    self._entrypoint = func._state_name
                    _found_initial = True
            if hasattr(func, "_is_background"):
                self._background_tasks.append(method)
            if hasattr(func, "_run_at_init"):
                self._initialization_tasks.append(method)
        if not _found_initial:
            raise NoInitialStateError()

    async def _start_background_tasks(self, vehicle: Vehicle) -> None:
        """
        Start all background tasks in the asyncio event loop.

        Args:
            vehicle: The vehicle instance.
        """
        for task in self._background_tasks:

            async def _task_runner(t: _BackgroundTask = task) -> None:
                """Run and automatically restart a background task on failure."""
                while self._running:
                    try:
                        await t.__func__(self, vehicle)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        logger.error(f"Background task {t.__name__} failed: {e}")
                        traceback.print_exc()
                        await asyncio.sleep(0.5)

            future = asyncio.ensure_future(_task_runner())
            self._background_task_futures.append(future)

    async def run(
        self,
        vehicle: Vehicle,
        build_before_running: bool = True,
    ) -> None:
        """
        Execute the state machine logic.

        Args:
            vehicle: The vehicle instance.
            build_before_running: Whether to call _build() first.
                Defaults to True.

        Raises:
            InvalidStateError: If the machine transitions to an unregistered state.
        """
        if build_before_running:
            self._build()
        if not self._entrypoint:
            raise NoInitialStateError()
        self._current_state = self._entrypoint
        self._next_state_overrides = []
        self._running = True

        if len(self._initialization_tasks) != 0:
            try:
                await asyncio.gather(*[f(vehicle) for f in self._initialization_tasks])
            except Exception as e:
                logger.error(f"StateMachine: at_init task failed: {e}", exc_info=True)
                for future in self._background_task_futures:
                    future.cancel()
                raise

        await self._start_background_tasks(vehicle)

        while self._running:
            if self._current_state not in self._states:
                raise InvalidStateError(self._current_state, list(self._states.keys()))

            from aerpawlib.cli.progress_bar import update_progress

            update_progress(
                f"Running state: {self._current_state}",
                completed=70,
                state=self._current_state,
            )

            next_state = await self._states[self._current_state].run(self, vehicle)
            if self._next_state_overrides:
                self._current_state = self._next_state_overrides.pop(0)
                logger.info(f"StateMachine: state transition (override) -> '{self._current_state}'")
            else:
                self._current_state = next_state

            if self._current_state is None:
                self.stop()
            await asyncio.sleep(STATE_MACHINE_DELAY_S)
        self._running = False
        for future in self._background_task_futures:
            future.cancel()
        if self._background_task_futures:
            await asyncio.gather(*self._background_task_futures, return_exceptions=True)

        self.cleanup()

    def stop(self) -> None:
        """
        Call `stop` to stop the execution of the `StateMachine` after
        completion of the current state. This is equivalent to returning `None`
        at the end of a state's execution.
        """
        self._running = False


class ZmqStateMachine(StateMachine):
    """StateMachine with remote ``transition_runner`` and ``query_field`` over ZMQ.

    See ``aerpawlib.v1.runner`` module documentation.
    """

    _exported_states: dict[str, _State]

    def _build(self) -> None:
        """Build base state maps and collect ZMQ-exposed states/fields."""
        super()._build()
        self._exported_states = {}
        self._exported_fields = {}
        self._zmq_state_aliases: dict[str, str] = {}
        for _name, method, func in self._get_decorated_methods():
            if hasattr(func, "_is_exposed_zmq"):
                if not hasattr(func, "_is_state"):
                    raise StateMachineError(
                        "@expose_zmq can only be used on @state/@timed_state methods",
                    )
                self._exported_states[func._zmq_name] = _State(
                    method,
                    func._state_name,
                )
                self._zmq_state_aliases[func._zmq_name] = func._state_name
            elif hasattr(func, "_is_exposed_field_zmq"):
                self._exported_fields[func._zmq_name] = method

    _zmq_identifier: str
    _zmq_proxy_server: str

    def _initialize_zmq_bindings(
        self,
        vehicle_identifier: str,
        proxy_server_addr: str,
        in_port: int | str | None = None,
        out_port: int | str | None = None,
    ) -> None:
        in_port = int(in_port if in_port is not None else ZMQ_PROXY_IN_PORT)
        out_port = int(out_port if out_port is not None else ZMQ_PROXY_OUT_PORT)
        if not check_zmq_proxy_reachable(proxy_server_addr, in_port=in_port, out_port=out_port):
            raise ConnectionError(
                f"ZMQ proxy at {proxy_server_addr}:{in_port}/{out_port} is not reachable. Ensure the proxy is started before this runner (aerpawlib-run-proxy) and both ports are open.",
            )
        logger.info("ZMQ proxy TCP ports open at %s (:%s/:%s)", proxy_server_addr, in_port, out_port)
        self._zmq_identifier = vehicle_identifier
        self._zmq_proxy_server = proxy_server_addr
        self._zmq_transport = ZmqTransport(
            vehicle_identifier,
            proxy_server_addr,
            in_port=in_port,
            out_port=out_port,
        )
        self._zmq_pending_queries: dict[str, dict[str, Any]] = {}
        self._zmq_handle_vehicle: Vehicle | None = None
        # Aliases kept for unit tests that inspect internal names.
        self._zmq_context = None
        self._zmq_received_fields: dict[str, dict[str, Any]] = {}

    def _resolve_transition_state(self, next_state: str) -> str | None:
        if not self._states:
            self._build()
        aliases = getattr(self, "_zmq_state_aliases", {})
        resolved = aliases.get(next_state, next_state)
        if resolved not in self._states:
            logger.warning(
                "ZmqStateMachine: ignoring unknown transition %r (resolved %r)",
                next_state,
                resolved,
            )
            return None
        return resolved

    async def _zmq_handle_request(
        self,
        vehicle: Vehicle,
        message: dict[str, Any],
    ) -> None:
        msg_type = message.get("msg_type")

        if msg_type == ZMQ_TYPE_TRANSITION:
            next_state = message.get("next_state")
            if not next_state:
                logger.warning(
                    "ZmqStateMachine: TRANSITION message missing 'next_state'",
                )
                return
            resolved = self._resolve_transition_state(str(next_state))
            if resolved is None:
                return
            self._next_state_overrides.append(resolved)
            logger.info(f"ZmqStateMachine: queued state override -> '{resolved}'")
        elif msg_type == ZMQ_TYPE_FIELD_REQUEST:
            field = message.get("field")
            sender = message.get("from")
            if not field or not sender:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_REQUEST (missing 'field' or 'from')",
                )
                return
            req_id = message.get("req_id")
            try:
                return_val = None
                if field in self._exported_fields:
                    return_val = await self._exported_fields[field](vehicle)
                await self._reply_queried_field(sender, field, return_val, req_id=req_id)
            except Exception as e:
                logger.error("ZmqStateMachine: field handler %r failed: %s", field, e, exc_info=True)
                await self._reply_queried_field(sender, field, None, req_id=req_id, error=str(e))
        elif msg_type == ZMQ_TYPE_FIELD_CALLBACK:
            field = message.get("field")
            msg_from = message.get("from")
            if not field or msg_from is None:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_CALLBACK (missing 'field' or 'from')",
                )
                return
            from aerpawlib.v1.util import Coordinate, VectorNED

            value = decode_value(
                message.get("value"),
                coordinate_cls=Coordinate,
                vector_cls=VectorNED,
            )
            req_id = message.get("req_id")
            if isinstance(req_id, str) and req_id in self._zmq_pending_queries:
                pending = self._zmq_pending_queries[req_id]
                pending["value"] = value
                pending["error"] = message.get("error")
                pending["event"].set()
                return
            if msg_from not in self._zmq_received_fields:
                self._zmq_received_fields[msg_from] = {}
            self._zmq_received_fields[msg_from][field] = value

    async def _on_zmq_message(self, message: dict[str, Any]) -> None:
        vehicle = self._zmq_handle_vehicle
        if vehicle is None:
            return
        await self._zmq_handle_request(vehicle, message)

    async def run(
        self,
        vehicle: Vehicle,
        zmq_proxy: bool = False,
    ) -> None:
        self._build()

        if getattr(self, "_zmq_identifier", None) is None or getattr(self, "_zmq_proxy_server", None) is None:
            raise StateMachineError(
                "ZMQ bindings not initialized. Pass --zmq-identifier and --zmq-proxy-server when running (e.g. --zmq-identifier leader --zmq-proxy-server 127.0.0.1)",
            )

        self._zmq_handle_vehicle = vehicle
        transport: ZmqTransport = self._zmq_transport
        transport.set_handler(self._on_zmq_message)
        await transport.start()
        try:
            await super().run(vehicle, build_before_running=False)
        finally:
            await transport.stop()

    async def wait_for_peers(
        self,
        identifiers: list[str],
        timeout: float = 30.0,
    ) -> None:
        """Block until each identifier has sent HELLO."""
        await self._zmq_transport.wait_for_peers(identifiers, timeout=timeout)

    async def transition_runner(
        self,
        identifier: str,
        state: str,
        timeout: float = ZMQ_TRANSITION_TIMEOUT_S,
    ) -> None:
        if not getattr(self, "_zmq_transport", None) or not self._zmq_transport.started:
            raise RuntimeError("ZMQ not initialized; call _initialize_zmq_bindings first")
        await self._zmq_transport.send(
            {
                "msg_type": ZMQ_TYPE_TRANSITION,
                "from": self._zmq_identifier,
                "identifier": identifier,
                "next_state": state,
            },
            reliable=True,
            timeout=timeout,
        )

    async def query_field(
        self,
        identifier: str,
        field: str,
        timeout: float = ZMQ_QUERY_FIELD_TIMEOUT_S,
    ) -> Any:
        if not getattr(self, "_zmq_transport", None) or not self._zmq_transport.started:
            raise RuntimeError("ZMQ not initialized; call _initialize_zmq_bindings first")
        import uuid

        req_id = uuid.uuid4().hex
        event = asyncio.Event()
        self._zmq_pending_queries[req_id] = {"event": event, "value": None, "error": None}
        try:
            await self._zmq_transport.send(
                {
                    "msg_type": ZMQ_TYPE_FIELD_REQUEST,
                    "from": self._zmq_identifier,
                    "identifier": identifier,
                    "field": field,
                    "req_id": req_id,
                },
                reliable=True,
                timeout=timeout,
            )
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            raise
        finally:
            pending = self._zmq_pending_queries.pop(req_id, None)
        if pending is None:
            raise TimeoutError(f"ZMQ query_field {identifier}.{field} lost pending state")
        if pending.get("error"):
            raise RuntimeError(f"Remote field {identifier}.{field} failed: {pending['error']}")
        return pending["value"]

    async def _reply_queried_field(
        self,
        identifier: str,
        field: str,
        value: Any,
        req_id: str | None = None,
        error: str | None = None,
    ) -> None:
        reply_obj = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": self._zmq_identifier,
            "identifier": identifier,
            "field": field,
            "value": value,
        }
        if req_id is not None:
            reply_obj["req_id"] = req_id
        if error is not None:
            reply_obj["error"] = error
        await self._zmq_transport.send(reply_obj, reliable=False)
