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

import zmq
import zmq.asyncio

from aerpawlib.v1.constants import (
    STATE_MACHINE_DELAY_S,
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_QUERY_FIELD_TIMEOUT_S,
    ZMQ_TYPE_FIELD_CALLBACK,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_GOODBYE,
    ZMQ_TYPE_HELLO,
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
from aerpawlib.v1.zmqutil import check_zmq_proxy_reachable

from .decorators import _State, background

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
        for _name, method, func in self._get_decorated_methods():
            if hasattr(func, "_is_exposed_zmq"):
                if not hasattr(func, "_is_state"):
                    raise StateMachineError(
                        "@expose_zmq can only be used on @state/@timed_state methods",
                    )
                self._exported_states[func._zmq_name] = _State(
                    method,
                    func._zmq_name,
                )
            elif hasattr(func, "_is_exposed_field_zmq"):
                self._exported_fields[func._zmq_name] = method

    _zmq_identifier: str
    _zmq_proxy_server: str

    _ZMQ_FIELD_PENDING = object()

    def _initialize_zmq_bindings(
        self,
        vehicle_identifier: str,
        proxy_server_addr: str,
    ) -> None:
        if not check_zmq_proxy_reachable(proxy_server_addr):
            raise ConnectionError(f"ZMQ proxy at {proxy_server_addr} is not reachable. Ensure the proxy is started before this runner (aerpawlib-run-proxy).")
        logger.info("Successfully connected to ZMQ proxy at %s", proxy_server_addr)
        self._zmq_identifier = vehicle_identifier
        self._zmq_proxy_server = proxy_server_addr
        self._zmq_context = zmq.asyncio.Context()
        self._zmq_messages_sending = asyncio.Queue()
        self._zmq_received_fields = {}

    @background
    async def _zmq_bg_sub(self, vehicle: Vehicle) -> None:
        socket = zmq.asyncio.Socket(
            context=self._zmq_context,
            io_loop=asyncio.get_running_loop(),
            socket_type=zmq.SUB,
        )
        socket.setsockopt_string(zmq.SUBSCRIBE, "")

        socket.connect(f"tcp://{self._zmq_proxy_server}:{ZMQ_PROXY_OUT_PORT}")

        async def _handle(msg):
            try:
                await self._zmq_handle_request(vehicle, msg)
            except Exception as e:
                logger.error(f"Error handling ZMQ message: {e}", exc_info=True)

        try:
            while self._running:
                message = await socket.recv_pyobj()
                logger.debug(f"Received ZMQ message: {message}")
                if message.get("identifier") != self._zmq_identifier:
                    continue
                asyncio.create_task(_handle(message))
        finally:
            socket.close()

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
            self._next_state_overrides.append(next_state)
            logger.info(f"ZmqStateMachine: queued state override -> '{next_state}'")
        elif msg_type == ZMQ_TYPE_FIELD_REQUEST:
            field = message.get("field")
            sender = message.get("from")
            if not field or not sender:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_REQUEST (missing 'field' or 'from')",
                )
                return
            return_val = None
            if field in self._exported_fields:
                return_val = await self._exported_fields[field](vehicle)
            await self._reply_queried_field(sender, field, return_val)
        elif msg_type == ZMQ_TYPE_FIELD_CALLBACK:
            field = message.get("field")
            msg_from = message.get("from")
            if not field or msg_from is None:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_CALLBACK (missing 'field' or 'from')",
                )
                return
            value = message.get("value")
            if msg_from not in self._zmq_received_fields:
                self._zmq_received_fields[msg_from] = {}
            self._zmq_received_fields[msg_from][field] = value

    @background
    async def _zmq_bg_pub(self, _: Vehicle) -> None:
        socket = zmq.asyncio.Socket(
            context=self._zmq_context,
            io_loop=asyncio.get_running_loop(),
            socket_type=zmq.PUB,
        )
        socket.connect(f"tcp://{self._zmq_proxy_server}:{ZMQ_PROXY_IN_PORT}")
        try:
            hello_msg = {
                "msg_type": ZMQ_TYPE_HELLO,
                "from": self._zmq_identifier,
            }
            await socket.send_pyobj(hello_msg)
        except Exception as e:
            logger.warning("ZmqStateMachine: failed to send hello message: %s", e)

        try:
            while self._running:
                msg_sending = await self._zmq_messages_sending.get()
                await socket.send_pyobj(msg_sending)
        finally:
            try:
                goodbye_msg = {
                    "msg_type": ZMQ_TYPE_GOODBYE,
                    "from": self._zmq_identifier,
                }
                await asyncio.wait_for(socket.send_pyobj(goodbye_msg), timeout=0.2)
            except Exception:
                pass
            socket.close()

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

        await super().run(vehicle, build_before_running=False)

    async def transition_runner(self, identifier: str, state: str) -> None:
        transition_obj = {
            "msg_type": ZMQ_TYPE_TRANSITION,
            "from": self._zmq_identifier,
            "identifier": identifier,
            "next_state": state,
        }
        await self._zmq_messages_sending.put(transition_obj)

    async def query_field(
        self,
        identifier: str,
        field: str,
        timeout: float = ZMQ_QUERY_FIELD_TIMEOUT_S,
    ) -> Any:
        if identifier not in self._zmq_received_fields:
            self._zmq_received_fields[identifier] = {}
        self._zmq_received_fields[identifier][field] = self._ZMQ_FIELD_PENDING
        query_obj = {
            "msg_type": ZMQ_TYPE_FIELD_REQUEST,
            "from": self._zmq_identifier,
            "identifier": identifier,
            "field": field,
        }
        await self._zmq_messages_sending.put(query_obj)

        async def _wait_for_reply() -> None:
            """Wait until the requested field value is received."""
            while self._zmq_received_fields[identifier][field] is self._ZMQ_FIELD_PENDING:
                await asyncio.sleep(0.01)

        try:
            await asyncio.wait_for(
                _wait_for_reply(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._zmq_received_fields[identifier].pop(field, None)
            raise
        return self._zmq_received_fields[identifier][field]

    async def _reply_queried_field(
        self,
        identifier: str,
        field: str,
        value: Any,
    ) -> None:
        reply_obj = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": self._zmq_identifier,
            "identifier": identifier,
            "field": field,
            "value": value,
        }
        await self._zmq_messages_sending.put(reply_obj)
