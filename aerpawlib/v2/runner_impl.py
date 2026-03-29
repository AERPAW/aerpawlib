"""Runner, BasicRunner, StateMachine, and ZmqStateMachine implementations."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, TypeVar

import zmq
import zmq.asyncio

from .constants import (
    STATE_MACHINE_DELAY_S,
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_QUERY_FIELD_TIMEOUT_S,
    ZMQ_TYPE_TRANSITION,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_FIELD_CALLBACK,
)
from .exceptions import (
    InvalidStateError,
    NoEntrypointError,
    NoInitialStateError,
    RunnerError,
    UnexpectedDisarmError,
)
from .log import LogComponent, get_logger
from .runner_config import (
    BasicRunnerConfig,
    StateMachineConfig,
    StateSpec,
    ZmqStateMachineConfig,
    V,
)
from .zmqutil import check_zmq_proxy_reachable

logger = get_logger(LogComponent.RUNNER)


class Runner:
    """Base execution framework for aerpawlib v2 scripts."""

    def set_event_log(self, event_log: Any) -> None:
        """Set the structured event logger for mission events."""
        self._event_log = event_log

    async def run(self, vehicle: V) -> None:
        """Execute the runner's core logic.

        Args:
            vehicle: The connected vehicle instance.
        """
        pass

    def initialize_args(self, args: List[str]) -> None:
        """Parse additional CLI arguments.

        Args:
            args: List of unrecognised argument strings passed from the CLI.
        """
        pass

    def cleanup(self) -> None:
        """Cleanup on exit."""
        pass

    async def _run_with_disarm_guard(self, vehicle: Any, coro) -> None:
        """Run *coro* but raise UnexpectedDisarmError if the vehicle disarms unexpectedly.

        Uses ``asyncio.wait(FIRST_COMPLETED)`` to race the main coroutine against the
        vehicle's unexpected-disarm event.  If the event fires first the main task is
        cancelled and ``UnexpectedDisarmError`` is raised so the experiment terminates
        cleanly.  If the vehicle object has no ``_unexpected_disarm_event`` attribute
        (e.g. DummyVehicle in tests) the coro is awaited directly without the guard.
        """
        disarm_event = getattr(vehicle, "_unexpected_disarm_event", None)
        if disarm_event is None:
            await coro
            return

        main_task = asyncio.ensure_future(coro)

        async def _watch_disarm() -> None:
            await disarm_event.wait()

        disarm_task = asyncio.ensure_future(_watch_disarm())

        try:
            done, pending = await asyncio.wait(
                [main_task, disarm_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            main_task.cancel()
            disarm_task.cancel()
            raise

        disarm_triggered = disarm_task in done and main_task in pending

        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        if disarm_triggered:
            raise UnexpectedDisarmError()

        if main_task.done() and not main_task.cancelled():
            exc = main_task.exception()
            if exc is not None:
                raise exc


class BasicRunner(Runner):
    """Single entry point runner."""

    async def run(self, vehicle: Any) -> None:
        """Run the decorated entrypoint method.

        Args:
            vehicle: The connected vehicle instance passed to the entrypoint.

        Raises:
            NoEntrypointError: If no @entrypoint was declared on the class.
        """
        config = getattr(self.__class__, "config", None)
        if not isinstance(config, BasicRunnerConfig):
            raise NoEntrypointError()
        name = config.entrypoint
        method = getattr(self, name, None)
        if method is None:
            raise NoEntrypointError()
        logger.info(f"BasicRunner: starting entrypoint '{name}'")
        try:
            await self._run_with_disarm_guard(vehicle, method(vehicle))
            logger.info(f"BasicRunner: entrypoint '{name}' completed")
        except Exception as e:
            logger.error(f"BasicRunner: entrypoint '{name}' failed: {e}")
            raise
        finally:
            self.cleanup()


class StateMachine(Runner):
    """State-based mission runner."""

    def __init__(self) -> None:
        self._current_state: Optional[str] = None
        self._running = False
        self._background_futures: List[asyncio.Future] = []

    def _get_config(self) -> StateMachineConfig:
        """Return the StateMachineConfig for this class.

        Raises:
            NoInitialStateError: If no config is present.
        """
        config = getattr(self.__class__, "config", None)
        if not isinstance(config, StateMachineConfig):
            raise NoInitialStateError()
        return config

    def _get_states(self) -> Dict[str, StateSpec]:
        """Return a mapping of state name to StateSpec for this runner.

        Returns:
            Dict mapping state name strings to their StateSpec metadata.
        """
        cfg = self._get_config()
        return {s.name: s for s in cfg.states}

    def _get_initial_state(self) -> str:
        """Return the name of the initial state.

        Returns:
            Name of the state marked with first=True.

        Raises:
            NoInitialStateError: If no initial state was declared.
        """
        cfg = self._get_config()
        if not cfg.initial_state:
            raise NoInitialStateError()
        return cfg.initial_state

    def _get_backgrounds(self) -> List[str]:
        """Return method names registered as background tasks.

        Returns:
            List of method name strings for @background-decorated methods.
        """
        return self._get_config().backgrounds

    def _get_at_init(self) -> List[str]:
        """Return method names registered to run at initialisation.

        Returns:
            List of method name strings for @at_init-decorated methods.
        """
        return self._get_config().at_init

    async def _run_state(self, spec: StateSpec, vehicle: Any) -> str:
        """Execute a single state and return the name of the next state.

        For timed states the method runs (optionally in a loop) for ``spec.duration``
        seconds before the next state name is returned.

        Args:
            spec: Metadata describing the state to run.
            vehicle: The vehicle instance passed to the state method.

        Returns:
            Name of the next state, or an empty string / None to stop the machine.
        """
        method = getattr(self, spec.method_name)
        logger.debug(f"StateMachine: entering state '{spec.name}'")
        if spec.duration <= 0:
            next_state = await method(vehicle)
            return next_state
        stop_event = asyncio.Event()
        last_state = ""

        async def _bg() -> str:
            nonlocal last_state
            while not stop_event.is_set():
                last_state = await method(vehicle)
                if stop_event.is_set():
                    break
                if not spec.loop:
                    stop_event.set()
                    break
                await asyncio.sleep(STATE_MACHINE_DELAY_S)
            return last_state

        task = asyncio.create_task(_bg())
        logger.debug(
            f"StateMachine: timed_state '{spec.name}' "
            f"(duration={spec.duration}s, loop={spec.loop})"
        )
        await asyncio.sleep(spec.duration)
        stop_event.set()
        next_state = await task
        return next_state

    async def run(self, vehicle: Any) -> None:
        """Run the state machine from the initial state to completion.

        Executes at_init tasks, starts background tasks, then iterates
        through states until a state returns None or stop() is called.

        Args:
            vehicle: The connected vehicle instance passed to each state method.

        Raises:
            NoInitialStateError: If no initial state was declared.
            InvalidStateError: If a state transition targets an unknown state.
        """
        states = self._get_states()
        self._background_futures = []
        self._current_state = self._get_initial_state()
        self._running = True
        logger.info(
            f"StateMachine: starting with initial state '{self._current_state}' "
            f"(states: {list(states.keys())})"
        )

        async def _main_loop() -> None:
            at_init_list = self._get_at_init()
            if at_init_list:
                logger.debug(
                    f"StateMachine: running {len(at_init_list)} at_init task(s)"
                )
            for name in at_init_list:
                logger.debug(f"StateMachine: at_init '{name}'")
                method = getattr(self, name)
                await method(vehicle)

            backgrounds = self._get_backgrounds()
            if backgrounds:
                logger.info(
                    f"StateMachine: starting {len(backgrounds)} background task(s)"
                )
            MAX_BACKGROUND_RETRIES = 10
            for name in backgrounds:
                method = getattr(self, name)

                async def _bg_task(task, _name=name):
                    """Run a background task with bounded retry/backoff on errors."""
                    consecutive_failures = 0
                    while self._running:
                        try:
                            await task(vehicle)
                            consecutive_failures = 0
                        except asyncio.CancelledError:
                            return
                        except Exception as e:
                            consecutive_failures += 1
                            if consecutive_failures >= MAX_BACKGROUND_RETRIES:
                                logger.error(
                                    f"Background task '{_name}' exceeded max retries "
                                    f"({MAX_BACKGROUND_RETRIES}), stopping.",
                                    exc_info=True,
                                )
                                return
                            backoff = min(0.5 * (2 ** (consecutive_failures - 1)), 30)
                            logger.error(
                                f"Background task '{_name}' failed (attempt "
                                f"{consecutive_failures}/{MAX_BACKGROUND_RETRIES}), "
                                f"retrying in {backoff:.1f}s: {e}",
                                exc_info=True,
                            )
                            await asyncio.sleep(backoff)

                fut = asyncio.create_task(_bg_task(method))
                self._background_futures.append(fut)

            while self._running:
                if self._current_state not in states:
                    logger.error(
                        f"StateMachine: invalid state '{self._current_state}' "
                        f"(valid: {list(states.keys())})"
                    )
                    raise InvalidStateError(self._current_state, list(states.keys()))
                spec = states[self._current_state]
                next_state = await self._run_state(spec, vehicle)
                if getattr(self, "_override_next_state_transition", False):
                    self._override_next_state_transition = False
                    self._current_state = getattr(self, "_next_state_overr", next_state)
                    logger.info(
                        f"StateMachine: state transition (override) -> '{self._current_state}'"
                    )
                else:
                    self._current_state = next_state
                    logger.info(
                        f"StateMachine: state transition '{spec.name}' -> '{next_state}'"
                    )
                if self._current_state is None:
                    logger.info(f"StateMachine: completed (final state returned None)")
                    break
                await asyncio.sleep(STATE_MACHINE_DELAY_S)

        try:
            await self._run_with_disarm_guard(vehicle, _main_loop())
        finally:
            self._running = False
            logger.info("StateMachine: stopping")

            for fut in self._background_futures:
                fut.cancel()
            if self._background_futures:
                await asyncio.gather(*self._background_futures, return_exceptions=True)
            self.cleanup()

    def stop(self) -> None:
        """Stop the state machine after current state."""
        logger.debug(
            f"StateMachine: stop() called (current state: {self._current_state})"
        )
        self._running = False


class ZmqStateMachine(StateMachine):
    """
    StateMachine with ZMQ-based remote control.

    Improvements over original implementation:
    - Messages are processed sequentially (inline in recv loop, not via
      asyncio.create_task), eliminating concurrent-handler ordering issues.
    - asyncio.Event per pending field reply replaces the busy-poll loop.
    - All message key accesses use .get() to avoid KeyError on malformed messages.
    - ZMQ context is destroyed cleanly in run()'s finally block.
    - Send and receive loops are named _zmq_recv_loop / _zmq_send_loop to
      avoid collisions with user-defined @background methods.

    Requires _initialize_zmq_bindings(vehicle_identifier, proxy_server_addr)
    before run().
    """

    def __init__(self) -> None:
        super().__init__()
        self._zmq_identifier: Optional[str] = None
        self._zmq_proxy_server: Optional[str] = None
        self._zmq_context: Optional[zmq.asyncio.Context] = None
        self._zmq_send_queue: Optional[asyncio.Queue] = None
        self._zmq_pending_fields: Dict[str, Dict[str, Any]] = {}
        self._override_next_state_transition: bool = False
        self._next_state_overr: str = ""

    def _initialize_zmq_bindings(
        self, vehicle_identifier: str, proxy_server_addr: str
    ) -> None:
        """Configure ZMQ connection. Call before run()."""
        if not check_zmq_proxy_reachable(proxy_server_addr):
            logger.warning(
                "ZMQ proxy at %s is not reachable. Ensure the proxy is started "
                "before this runner (run_zmq_proxy in a separate process).",
                proxy_server_addr,
            )
        self._zmq_identifier = vehicle_identifier
        self._zmq_proxy_server = proxy_server_addr
        self._zmq_context = zmq.asyncio.Context()
        self._zmq_send_queue = None
        self._zmq_pending_fields = {}
        self._override_next_state_transition = False
        self._next_state_overr = ""

    def _get_zmq_config(self) -> ZmqStateMachineConfig:
        """Return validated ZMQ configuration for this runner class."""
        cfg = getattr(self.__class__, "config", None)
        if not isinstance(cfg, ZmqStateMachineConfig):
            raise RunnerError("ZmqStateMachine requires config from @state/@expose_zmq")
        return cfg

    async def _zmq_recv_loop(self, vehicle: Any) -> None:
        """Subscribe to the ZMQ proxy and handle messages sequentially.

        Args:
            vehicle: The vehicle instance, passed to field-request handlers.
        """
        ctx = self._zmq_context
        if ctx is None or self._zmq_proxy_server is None:
            return
        sock = ctx.socket(zmq.SUB)
        sock.connect(f"tcp://{self._zmq_proxy_server}:{ZMQ_PROXY_OUT_PORT}")
        sock.setsockopt_string(zmq.SUBSCRIBE, "")
        try:
            while self._running:
                try:
                    message = await sock.recv_pyobj()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"ZmqStateMachine: recv error: {e}")
                    continue
                if message.get("identifier") != self._zmq_identifier:
                    continue
                await self._zmq_handle_message(vehicle, message)
        finally:
            sock.close()

    async def _zmq_send_loop(self, vehicle: Any) -> None:
        """Publish ZMQ messages from the internal send queue.

        Args:
            vehicle: Unused; present for background-task signature compatibility.
        """
        ctx = self._zmq_context
        if ctx is None or self._zmq_proxy_server is None:
            return
        sock = ctx.socket(zmq.PUB)
        sock.connect(f"tcp://{self._zmq_proxy_server}:{ZMQ_PROXY_IN_PORT}")
        try:
            while self._running:
                try:
                    msg = await self._zmq_send_queue.get()
                except asyncio.CancelledError:
                    raise
                await sock.send_pyobj(msg)
        finally:
            sock.close()

    async def _zmq_handle_message(self, vehicle: Any, message: dict) -> None:
        """
        Handle one incoming ZMQ message.

        Called inline from _zmq_recv_loop (sequential, never concurrent), so no
        locking is needed for shared state mutation.
        """
        msg_type = message.get("msg_type")

        if msg_type == ZMQ_TYPE_TRANSITION:
            next_state = message.get("next_state")
            if not next_state:
                logger.warning(
                    "ZmqStateMachine: TRANSITION message missing 'next_state'"
                )
                return
            self._next_state_overr = next_state
            self._override_next_state_transition = True
            logger.info(f"ZmqStateMachine: queued state override -> '{next_state}'")

        elif msg_type == ZMQ_TYPE_FIELD_REQUEST:
            field = message.get("field")
            sender = message.get("from")
            if not field or not sender:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_REQUEST "
                    "(missing 'field' or 'from')"
                )
                return
            cfg = self._get_zmq_config()
            return_val = None
            if field in cfg.exposed_fields:
                method = getattr(self, cfg.exposed_fields[field])
                return_val = await method(vehicle)
            await self._zmq_send_reply(sender, field, return_val)

        elif msg_type == ZMQ_TYPE_FIELD_CALLBACK:
            field = message.get("field")
            sender = message.get("from")
            if not field or sender is None:
                logger.warning(
                    "ZmqStateMachine: malformed FIELD_CALLBACK "
                    "(missing 'field' or 'from')"
                )
                return
            value = message.get("value")
            pending = self._zmq_pending_fields.get(sender, {})
            waiting = pending.get(field)
            if isinstance(waiting, asyncio.Event):
                pending[field] = value
                waiting.set()
            else:
                if sender not in self._zmq_pending_fields:
                    self._zmq_pending_fields[sender] = {}
                self._zmq_pending_fields[sender][field] = value

    def _get_backgrounds(self) -> List[str]:
        """Return base backgrounds plus mandatory ZMQ send/receive loops."""
        base = list(super()._get_backgrounds())
        if "_zmq_recv_loop" not in base:
            base.insert(0, "_zmq_recv_loop")
        if "_zmq_send_loop" not in base:
            base.insert(1, "_zmq_send_loop")
        return base

    async def run(self, vehicle: Any) -> None:
        """Run with ZMQ. Requires _initialize_zmq_bindings first."""
        if self._zmq_identifier is None or self._zmq_proxy_server is None:
            raise RunnerError(
                "ZmqStateMachine requires _initialize_zmq_bindings before run. "
                "Pass --zmq-identifier and --zmq-proxy-server."
            )
        if self._zmq_send_queue is None:
            self._zmq_send_queue = asyncio.Queue()
        try:
            await super().run(vehicle)
        finally:
            if self._zmq_context is not None:
                self._zmq_context.destroy(linger=0)
                self._zmq_context = None

    async def transition_runner(self, identifier: str, state_name: str) -> None:
        """Send a ZMQ state-transition command to another runner.

        Args:
            identifier: ZMQ identifier of the target runner.
            state_name: Name of the state to transition the target runner into.
        """
        if self._zmq_send_queue is None:
            return
        await self._zmq_send_queue.put(
            {
                "msg_type": ZMQ_TYPE_TRANSITION,
                "from": self._zmq_identifier,
                "identifier": identifier,
                "next_state": state_name,
            }
        )

    async def query_field(
        self, identifier: str, field: str, timeout: float = ZMQ_QUERY_FIELD_TIMEOUT_S
    ) -> Any:
        """Query a field from another ZMQ runner and return the value.

        Uses asyncio.Event to block until the reply arrives (no busy-poll).

        Args:
            identifier: ZMQ identifier of the target runner.
            field: Name of the exposed field to query.
            timeout: Maximum seconds to wait for a reply.

        Returns:
            The value returned by the remote runner's @expose_field_zmq method.

        Raises:
            RuntimeError: If ZMQ has not been initialised via
                _initialize_zmq_bindings.
            asyncio.TimeoutError: If the reply does not arrive within timeout.
        """
        if self._zmq_send_queue is None:
            raise RuntimeError(
                "ZMQ not initialized; call _initialize_zmq_bindings first"
            )
        if identifier not in self._zmq_pending_fields:
            self._zmq_pending_fields[identifier] = {}
        event = asyncio.Event()
        self._zmq_pending_fields[identifier][field] = event
        await self._zmq_send_queue.put(
            {
                "msg_type": ZMQ_TYPE_FIELD_REQUEST,
                "from": self._zmq_identifier,
                "identifier": identifier,
                "field": field,
            }
        )
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._zmq_pending_fields.get(identifier, {}).pop(field, None)
            raise
        value = self._zmq_pending_fields[identifier].pop(field)
        return value

    async def _zmq_send_reply(self, identifier: str, field: str, value: Any) -> None:
        """Send a field-query reply to the requesting runner.

        Args:
            identifier: ZMQ identifier of the requesting runner.
            field: The field name that was queried.
            value: The value to send back.
        """
        if self._zmq_send_queue is None:
            return
        await self._zmq_send_queue.put(
            {
                "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
                "from": self._zmq_identifier,
                "identifier": identifier,
                "field": field,
                "value": value,
            }
        )
