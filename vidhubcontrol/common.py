import enum
import asyncio
from typing import Optional, Any, Union
from loguru import logger

from pydispatch import Dispatcher

class ConnectionState(enum.IntFlag):
    r"""Enum to describe various connection states

    Members may be combined using bitwise operators (&, \|, ^, ~)
    """
    not_connected = 1
    """Indicates there is no connection and no connection attempts are being made
    """

    connecting = 2
    """Indicates an attempt to connect is being made
    """

    disconnecting = 4
    """Indicates the connection is being closed
    """

    connected = 8
    """Indicates the connection is active
    """

    failure = 16
    """Indicates an error occured
    """

    waiting = connecting | disconnecting
    """Indicates the connection is either :attr:`connecting` or :attr:`disconnecting`
    """

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

        >>> from vidhubcontrol.common import ConnectionState
        >>> ConnectionState.connected | ConnectionState.not_connected
        <ConnectionState.connected|not_connected: 9>
        >>> ConnectionState.disconnecting | ConnectionState.failure
        <ConnectionState.failure|disconnecting: 20>
        >>> # This combination is already defined as "waiting"
        >>> ConnectionState.connecting | ConnectionState.disconnecting
        <ConnectionState.waiting: 6>

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
        return format(self.value, format_spec)

    def __iter__(self):
        for member in ConnectionState:
            if member in self:
                yield member

StrOrState = Union[ConnectionState, str]

class ConnectionManager(Dispatcher):
    """A manager for tracking and waiting for :class:`connection states <ConnectionState>`

    A :class:`asyncio.Condition` is used to to notify any waiting tasks of
    changes to :attr:`state`. This requires the underlying lock to be
    :meth:`acquired <acquire>` before calling any of the waiter or setter methods
    and :meth:`released <release>` afterwards.

    This class supports the asynchronous context manager protocol for use in
    :keyword:`async with` statements.

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
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
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

        Raises:
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        await self._set_state(state)

    async def _set_state(self, state: StrOrState):
        if isinstance(state, str):
            state = ConnectionState.from_str(state)
        changed = False
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

        Raises:
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        await self._set_failure(reason, exc, state)

    async def _set_failure(
        self,
        reason: Any,
        exc: Optional[Exception] = None,
        state: Optional[StrOrState] = ConnectionState.disconnecting | ConnectionState.failure
    ):
        if isinstance(state, str):
            state = ConnectionState.from_str(state)
        assert ConnectionState.failure in state
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
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        return await self._wait(timeout)

    async def _wait(self, timeout: Optional[float] = None) -> ConnectionState:
        coro = self._condition.wait()
        if timeout is not None:
            await asyncio.wait_for(coro, timeout)
        else:
            await coro
        return self.state

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
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        return await self._wait_for(state, timeout)

    async def _wait_for(
        self,
        state: StrOrState,
        timeout: Optional[float] = None
    ) -> ConnectionState:
        if isinstance(state, str):
            state = ConnectionState.from_str(state)

        def predicate():
            if state.is_compound or self.state.is_compound:
                return state & self.state != 0
            return self.state == state
        if predicate():
            return self.state

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
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        return await self._wait_for_established(timeout)

    async def _wait_for_established(
        self, timeout: Optional[float] = None
    ) -> ConnectionState:
        state = ConnectionState.connected | ConnectionState.disconnecting
        result = await self._wait_for(state, timeout)
        if result & (ConnectionState.failure | ConnectionState.disconnecting):
            result = await self._wait_for(ConnectionState.not_connected, timeout)
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
            RuntimeError: If the lock is not :meth:`acquired <acquire>` before
                calling this method
        """
        return await self.wait_for(ConnectionState.not_connected, timeout)

    async def syncronize(self, other: 'ConnectionManager'):
        """Copy the :attr:`state` and failure values of another
        :class:`ConnectionManager`

        Note:
            The lock must **not** be acquired before calling this method.
        """
        async with other:
            async with self:
                self._syncronize(other)

    def _syncronize(self, other: 'ConnectionManager'):
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

    def locked(self) -> bool:
        """True if the lock is acquired
        """
        return self._lock.locked()

    async def acquire(self):
        """Acquire the lock

        This method blocks until the lock is unlocked, then sets it to locked
        and returns True.
        """
        return await self._lock.acquire()

    def release(self):
        """Release the lock

        Raises:
            RuntimeError: if called on an unlocked lock
        """
        self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        self.release()

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

    @property
    def other(self) -> Optional[ConnectionManager]:
        """The manager currently being syncronized to
        """
        return self.__other

    async def set_other(self, other: Optional[ConnectionManager]):
        """Set the manager to syncronize with

        This binds to the :func:`state_changed` event of *other* and calls the
        :meth:`~ConnectionManager.syncronize` method whenever the state of the
        other manager changes.

        If ``None`` is given, :attr:`~ConnectionManager.state` is set to
        :attr:`~ConnectionState.not_connected`

        Note:
            The lock must *not* be acquired before calling this method
        """
        async with self._instance_lock:
            cur = self.other
            if cur is other:
                return
            self.__other = other
            if cur is not None:
                cur.unbind(self)
            async with self:
                if other is None:
                    await self.set_state(ConnectionState.not_connected)
                else:
                    async with other:
                        self._syncronize(other)
                        loop = asyncio.get_event_loop()
                        other.bind_async(loop, state_changed=self._on_other_state_changed)

    async def _on_other_state_changed(self, instance, state, **kwargs):
        if self._instance_lock.locked() or self.other is not instance:
            return
        async with self._instance_lock:
            if self.other is not instance:
                return
            await self.syncronize(instance)
