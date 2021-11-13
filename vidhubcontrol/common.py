import enum
import asyncio
from typing import Optional, Any, Union
from loguru import logger

from pydispatch import Dispatcher

class ConnectionState(enum.IntFlag):
    r"""Enum to describe various connection states

    Members may be combined using bitwise operators (&, \|, ^, ~)
    """
    not_connected = 1                       #: Not connected
    connecting = 2                          #: Attempting to connect
    disconnecting = 4                       #: Disconnecting
    connected = 8                           #: Connected successfully
    failure = 16                            #: Failed to connect
    waiting = connecting | disconnecting    #: Connecting or disconnecting

    @property
    def is_compound(self) -> bool:
        """This will evaluate to True for states combined using bitwise operators
        """
        return self.name is None

    @property
    def is_connected(self) -> bool:
        """Convenience property evaluating as True if
        ``self == ConnectionState.connected``
        """
        return self == ConnectionState.connected

    @classmethod
    def from_str(cls, s: str) -> 'ConnectionState':
        r"""Create a :class:`ConnectionState` member by name(s)

        Combined states can be created by separating their names with a "\|"
        """
        if '|' in s:
            result = None
            for name in s.split('|'):
                if result is None:
                    result = cls.from_str(name)
                else:
                    result |= cls.from_str(name)
            return result
        s = s.lower()
        return getattr(cls, s)

    def __str__(self):
        if self.is_compound:
            return '|'.join((obj.name for obj in self))
        return self.name

    def __format__(self, format_spec):
        if format_spec == '':
            return str(self)
        return super().__format__(format_spec)

    def __iter__(self):
        for member in ConnectionState:
            if member in self:
                yield member

StrOrState = Union[ConnectionState, str]

class ConnectionManager(Dispatcher):
    """A manager for tracking and waiting for :class:`connection states <ConnectionState>`

    :Events:

        .. function:: state_changed(self: ConnectionManager, state: ConnectionState)

            Emitted when the value of :attr:`state` has changed

    """

    failure_reason: Optional[str]
    """A message describing errors (if encountered)"""

    failure_exception: Optional[Exception]
    """The :class:`Exception` raised if an error occured"""

    _events_ = ['state_changed']
    def __init__(self, initial: Optional[ConnectionState] = ConnectionState.not_connected):
        self.__state = initial
        self._condition = asyncio.Condition()
        self.failure_reason = None
        self.failure_exception = None

    @property
    def state(self) -> ConnectionState:
        """The current state
        """
        return self.__state

    async def set_state(self, state: StrOrState):
        """Set the :attr:`state` to the given value

        The *state* argument may be either a :class:`ConnectionState` member
        or a string. (see :meth:`ConnectionState.from_str`)
        """
        if isinstance(state, str):
            state = ConnectionState.from_str(state)
        changed = False
        async with self:
            if ConnectionState.failure in self.state:
                if state & (ConnectionState.connecting | ConnectionState.connected):
                    state &= ~ConnectionState.failure
                    self.failure_reason = None
                    self.failure_exception = None
                else:
                    state |= ConnectionState.failure
            if state != self.state:
                changed = True
                self.__state = state
                self._condition.notify_all()
        if changed:
            self.emit('state_changed', self, self.state)

    async def set_failure(
        self,
        reason: Any,
        exc: Optional[Exception] = None,
        state: Optional[StrOrState] = ConnectionState.disconnecting | ConnectionState.failure
    ):
        """Set :attr:`state` to indicate a failure

        Arguments:
            reason: A description of the failure
            exc: The Exception that caused the failure (if available)
            state: The new state to set. Must include :attr:`ConnectionState.failure`

        """
        if isinstance(state, str):
            state = ConnectionState.from_str(state)
        assert ConnectionState.failure in state
        async with self:
            self.__state = state
            self.failure_reason = reason
            self.failure_exception = exc
            self._condition.notify_all()
        self.emit('state_changed', self, self.state)

    async def wait(self, timeout: Optional[float] = None) -> ConnectionState:
        """Block until the next time :attr:`state` changes and return the value

        Arguments:
            timeout: If given, the number of seconds to wait. Otherwise, this
                will wait indefinitely

        Raises:
            asyncio.TimeoutError: If *timeout* is given and no state changes occured

        """
        async with self:
            coro = self._condition.wait()
            if timeout is not None:
                coro = asyncio.wait_for(coro, timeout)
            await coro
            result = self.state
        return result

    async def wait_for(
        self,
        state: StrOrState,
        timeout: Optional[float] = None
    ) -> ConnectionState:
        """Wait for a specific state

        The *state* argument may be a :class:`ConnectionState` member or string
        as described in :meth:`ConnectionState.from_str`.

        If the given state is :attr:`compound <ConnectionState.is_compound>`
        or the :attr:`state` is set as compound, this will wait until all
        members from the *state* argument are contained within the :attr:`state`
        value.

        Arguments:
            state: The state to wait for
            timeout: If given, the number of seconds to wait. Otherwise, this
                will wait indefinitely

        Raises:
            asyncio.TimeoutError: If *timeout* is given and no matching state
                changes were found

        """
        if isinstance(state, str):
            state = ConnectionState.from_str(state)

        def predicate():
            if state.is_compound or self.state.is_compound:
                return state & self.state != 0
            return self.state == state

        async with self:
            coro = self._condition.wait_for(predicate)
            if timeout is not None:
                coro = asyncio.wait_for(coro, timeout)
            await coro
            result = self.state
        if state.is_compound:
            return state & result
        return result

    async def wait_for_established(
        self, timeout: Optional[float] = None
    ) -> ConnectionState:
        """Wait for either a success (:attr:`ConnectionState.connected`) or
        failure (:attr:`ConnectionState.failure`)

        Arguments:
            timeout: If given, the number of seconds to wait. Otherwise, this
                will wait indefinitely

        Raises:
            asyncio.TimeoutError: If *timeout* is given and no matching state
                changes were found

        """
        state = ConnectionState.connected | ConnectionState.disconnecting
        result = await self.wait_for(state, timeout)
        if result & (ConnectionState.failure | ConnectionState.disconnecting):
            result = await self.wait_for(ConnectionState.not_connected, timeout)
        return result

    async def wait_for_disconnected(
        self, timeout: Optional[float] = None
    ) -> ConnectionState:
        """Wait for :attr:`ConnectionState.not_connected`

        Arguments:
            timeout: If given, the number of seconds to wait. Otherwise, this
                will wait indefinitely

        Raises:
            asyncio.TimeoutError: If *timeout* is given and no matching state
                changes were found
        """
        return await self.wait_for(ConnectionState.not_connected, timeout)

    async def syncronize(self, other: 'ConnectionManager'):
        """Copy the :attr:`state` and failure values of another
        :class:`ConnectionManager`
        """
        async with other:
            async with self:
                changed = False
                for attr in ('failure_reason', 'failure_exception', 'state'):
                    if getattr(self, attr) != getattr(other, attr):
                        changed = True
                        break
                if not changed:
                    return
                self.failure_reason = other.failure_reason
                self.failure_exception = other.failure_exception
                self.__state = other.state
                self._condition.notify_all()
        self.emit('state_changed', self, self.state)

    async def __aenter__(self):
        await self._condition.acquire()
        return self

    async def __aexit__(self, *args):
        self._condition.release()

    def __repr__(self):
        return f'<{self.__class__} at 0x{id(self):x}: {self}>'

    def __str__(self):
        return str(self.state)

class SyncronizedConnectionManager(ConnectionManager):
    """A connection manager that syncronizes itself with another
    """
    def __init__(self, initial: Optional[ConnectionState] = ConnectionState.not_connected):
        super().__init__(initial)
        self.__other = None
        self._instance_lock = asyncio.Lock()
        self._sync_task_started = asyncio.Event()
        self.sync_task = None

    @property
    def other(self) -> Optional[ConnectionManager]:
        """The manager currently being syncronized to
        """
        return self.__other

    async def set_other(self, other: Optional[ConnectionManager]):
        """Set the manager to syncronize with

        This creates a background :class:`~asyncio.Task` to
        :meth:`wait <ConnectionManager.wait>` for state changes and
        :meth:`syncronize <ConnectionManager.syncronize>` with the other manager.

        The background task will continue until another manager is set using this
        method or the :meth:`close` method is called.

        If ``None`` is given, :attr:`~ConnectionManager.state` is set to
        :attr:`~ConnectionState.not_connected` and the background task is stopped.
        """
        async with self._instance_lock:
            cur = self.other
            if cur is other:
                return
            self.__other = other
            if self.sync_task is not None:
                self.sync_task.cancel()
                try:
                    await self.sync_task
                except asyncio.CancelledError:
                    pass
                self.sync_task = None
                self._sync_task_started.clear()
            if other is None:
                await self.set_state(ConnectionState.not_connected)
            else:
                await self.syncronize(other)
                self.sync_task = asyncio.ensure_future(self.syncronize_loop(other))
                await self._sync_task_started.wait()

    async def close(self):
        """Stop any background syncronization tasks in use

        Note:
            This method must be called manually for graceful shutdown

        """
        await self.set_other(None)

    @logger.catch
    async def syncronize_loop(self, other: ConnectionManager):
        while self.other is other:
            self._sync_task_started.set()
            try:
                await asyncio.wait_for(other.wait(), 1)
            except asyncio.TimeoutError:
                pass
            if self._instance_lock.locked() or self.other is not other:
                break
            async with self._instance_lock:
                await self.syncronize(other)
