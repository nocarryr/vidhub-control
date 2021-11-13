import asyncio
import pytest
from vidhubcontrol.common import (
    ConnectionState, ConnectionManager, SyncronizedConnectionManager,
)


async def simulate_connect(connection, failure=False, reason='client unavailable'):
    await asyncio.sleep(.1)
    await connection.set_state(ConnectionState.connecting)
    assert ConnectionState.failure not in connection.state
    assert connection.failure_reason is None
    await asyncio.sleep(.5)
    if failure:
        await connection.set_failure(reason)
    else:
        await connection.set_state(ConnectionState.connected)

async def simulate_disconnect(connection):
    await asyncio.sleep(.1)
    await connection.set_state(ConnectionState.disconnecting)
    await asyncio.sleep(.5)
    await connection.set_state(ConnectionState.not_connected)

async def waiter(connection):
    states = []
    state = await connection.wait_for(ConnectionState.connecting, 10)
    print(f'waiter: {state}')
    states.append(state)
    while True:
        state = await connection.wait(10)
        print(f'waiter: {state}')
        states.append(state)
        if ConnectionState.not_connected in state:
            break
    return states

@pytest.mark.asyncio
async def test_connection_manager():

    connection = ConnectionManager()

    # Failed connect
    waiter_task = asyncio.ensure_future(waiter(connection))
    connect_task = asyncio.ensure_future(simulate_connect(connection, True))
    failure_wait_task = asyncio.ensure_future(connection.wait_for_established(10))

    state = await connection.wait_for(ConnectionState.disconnecting, 10)
    assert state == ConnectionState.disconnecting | ConnectionState.failure
    assert not state.is_connected
    assert connection.failure_reason == 'client unavailable'
    assert str(connection) == str(state)

    disconnect_task = asyncio.ensure_future(simulate_disconnect(connection))

    state = await failure_wait_task
    assert state == ConnectionState.not_connected | ConnectionState.failure
    assert not state.is_connected
    assert connection.failure_reason == 'client unavailable'

    await disconnect_task
    assert connection.failure_reason == 'client unavailable'

    expected_states = [
        ConnectionState.connecting,
        ConnectionState.disconnecting | ConnectionState.failure,
        ConnectionState.not_connected | ConnectionState.failure,
    ]
    expected_state_names = [
        'connecting', 'disconnecting|failure', 'not_connected|failure'
    ]
    states = await waiter_task
    assert states == expected_states
    names = [str(state) for state in states]
    assert names == expected_state_names
    assert [f'{state:02d}' for state in states] == [f'{state.value:02d}' for state in states]
    assert all([not state.is_connected for state in states])


    # Successful connect/disconnect
    waiter_task = asyncio.ensure_future(waiter(connection))
    connect_task = asyncio.ensure_future(simulate_connect(connection))

    state = await connection.wait_for_established(10)
    assert state == ConnectionState.connected
    assert state.is_connected
    assert connection.failure_reason is None

    await connect_task
    await asyncio.sleep(.5)
    disconnect_task = asyncio.ensure_future(simulate_disconnect(connection))

    state = await connection.wait_for_disconnected(10)
    assert state == ConnectionState.not_connected
    assert not state.is_connected

    await disconnect_task

    expected_states = [
        ConnectionState.connecting,
        ConnectionState.connected,
        ConnectionState.disconnecting,
        ConnectionState.not_connected,
    ]
    expected_state_names = [
        'connecting', 'connected', 'disconnecting', 'not_connected'
    ]

    states = await waiter_task
    assert states == expected_states
    names = [str(state) for state in states]
    assert names == expected_state_names
    assert [f'{state}' for state in states] == [state.name for state in states]

@pytest.mark.asyncio
async def test_syncronization():
    mgr1 = ConnectionManager()
    mgr2 = ConnectionManager()

    for state in ['connecting', 'connected', 'disconnecting', 'not_connected']:
        state = getattr(ConnectionState, state)
        await mgr1.set_state(state)
        await mgr2.syncronize(mgr1)
        assert mgr1.state == mgr2.state == state
        assert mgr1.failure_reason == mgr2.failure_reason == None
        assert mgr1.failure_exception is mgr2.failure_exception is None

    await mgr1.set_state(ConnectionState.connecting)
    await mgr2.syncronize(mgr1)
    assert mgr1.state == mgr2.state == ConnectionState.connecting

    exc = Exception('foo')
    await mgr1.set_failure('foo', exc)
    await mgr2.syncronize(mgr1)
    assert mgr2.state == mgr1.state == ConnectionState.failure | ConnectionState.disconnecting
    assert mgr1.failure_reason == mgr2.failure_reason == 'foo'
    assert mgr1.failure_exception is mgr2.failure_exception is exc

    await mgr1.set_state(ConnectionState.not_connected)
    await mgr2.syncronize(mgr1)
    assert mgr1.state == mgr2.state == ConnectionState.not_connected | ConnectionState.failure
    assert mgr1.failure_reason == mgr2.failure_reason == 'foo'
    assert mgr1.failure_exception is mgr2.failure_exception is exc

    await mgr1.set_state(ConnectionState.connecting)
    await mgr2.syncronize(mgr1)
    assert mgr1.state == mgr2.state == ConnectionState.connecting
    assert mgr1.failure_reason == mgr2.failure_reason == None
    assert mgr1.failure_exception is mgr2.failure_exception is None

@pytest.mark.asyncio
async def test_syncronized_manager():
    mgr1 = ConnectionManager()
    mgr2 = ConnectionManager()

    sync_mgr = SyncronizedConnectionManager()

    await mgr1.set_state('connecting')

    await sync_mgr.set_other(mgr1)
    assert sync_mgr.other is mgr1
    assert sync_mgr.state == mgr1.state == ConnectionState.connecting

    await mgr1.set_state('connected')
    await sync_mgr.wait_for('connected', 5)
    assert sync_mgr.state == mgr1.state == ConnectionState.connected

    await sync_mgr.set_other(mgr2)
    assert sync_mgr.other is mgr2
    assert sync_mgr.state == mgr2.state == ConnectionState.not_connected

    exc = Exception('foo')
    await mgr2.set_failure('foo', exc, 'not_connected|failure')
    state = await sync_mgr.wait()
    assert state == sync_mgr.state == mgr2.state == ConnectionState.not_connected | ConnectionState.failure
    assert sync_mgr.failure_reason == mgr2.failure_reason == 'foo'
    assert sync_mgr.failure_exception is mgr2.failure_exception is exc

    await sync_mgr.set_other(mgr1)
    await mgr2.set_state('not_connected')
    assert sync_mgr.state == mgr1.state == ConnectionState.connected
    assert sync_mgr.failure_reason == mgr1.failure_reason == None
    assert sync_mgr.failure_exception is mgr1.failure_exception is None

    await mgr1.set_state('disconnecting')
    state = await sync_mgr.wait()
    assert state == sync_mgr.state == mgr1.state == ConnectionState.disconnecting
    assert sync_mgr.failure_reason == mgr1.failure_reason == None
    assert sync_mgr.failure_exception is mgr1.failure_exception is None

    await sync_mgr.set_other(mgr2)
    assert sync_mgr.state == mgr2.state == ConnectionState.not_connected | ConnectionState.failure
    assert sync_mgr.failure_reason == mgr2.failure_reason == 'foo'
    assert sync_mgr.failure_exception is mgr2.failure_exception is exc

    await mgr1.set_state('connected')
    await mgr2.set_state('connecting')
    state = await sync_mgr.wait()
    assert state == sync_mgr.state == mgr2.state == ConnectionState.connecting
    assert sync_mgr.failure_reason == mgr2.failure_reason == None
    assert sync_mgr.failure_exception is mgr2.failure_exception is None

    await sync_mgr.set_other(None)
    assert sync_mgr.other is None
    assert sync_mgr.state == ConnectionState.not_connected

    await sync_mgr.set_other(mgr1)
    assert sync_mgr.state == mgr1.state == ConnectionState.connected
    assert sync_mgr.failure_reason == mgr1.failure_reason == None
    assert sync_mgr.failure_exception is mgr1.failure_exception is None

    await sync_mgr.close()

    assert sync_mgr.other is None
    assert sync_mgr.state == ConnectionState.not_connected
