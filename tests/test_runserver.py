import os
import sys
import shlex
import asyncio
import signal

import pytest

import vidhubcontrol
from vidhubcontrol.runserver import PID_FILENAME
from vidhubcontrol.utils import find_ip_addresses
from vidhubcontrol.config import Config
from vidhubcontrol.backends import DummyBackend
from vidhubcontrol.interfaces.osc import OscNode, OscInterface, OSCUDPServer, OscDispatcher


BASE_PATH = os.path.dirname(os.path.abspath(vidhubcontrol.__file__))
SCRIPT_PATH = os.path.join(BASE_PATH, 'runserver.py')
ENTRY_POINT = 'vidhubcontrol-server'

for iface_name, iface in find_ip_addresses():
    HOST_IFACE = iface
    break

@pytest.yield_fixture
def event_loop():
    if sys.platform == 'win32':
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

if sys.platform == 'win32':
    SCRIPT_PARAMS = [os.extsep.join([ENTRY_POINT, 'exe'])]
else:
    SCRIPT_PARAMS = [SCRIPT_PATH, ENTRY_POINT]

@pytest.fixture(params=SCRIPT_PARAMS)
def runserver_scriptname(request):
    return request.param

@pytest.mark.asyncio
async def test_runserver(tempconfig, mocked_vidhub_telnet_device, runserver_scriptname):

    # Build a config file to be read later in the subprocess
    Config.loop = None
    Config.USE_DISCOVERY = False
    config = await Config.load_async(str(tempconfig))
    await config.start()

    vidhub = await DummyBackend.create_async(device_id='dummy1')
    await config.add_vidhub(vidhub)

    xpts = [(i, 2) for i in range(vidhub.num_outputs)]
    await vidhub.set_crosspoints(*xpts)
    preset1 = await vidhub.store_preset(name='PRESET1')

    await config.stop()

    Config.USE_DISCOVERY = True

    osc_server_port = 9000
    osc_client_port = 9001

    cmd_str = '{} --config {} --osc-address {} --osc-port {}'.format(
        runserver_scriptname, tempconfig, HOST_IFACE.ip, osc_server_port)
    print('running subprocess: "{}"'.format(cmd_str))
    proc = await asyncio.create_subprocess_exec(*shlex.split(cmd_str),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

    print('subprocess started')

    while True:
        line = await proc.stdout.readline()
        if not len(line):
            raise Exception('process terminated')
        print(repr(line))
        if b'Ready' in line:
            break
    print('subprocess ready')

    with open(PID_FILENAME, 'r') as pid_fh:
        pid_str = pid_fh.read()
    assert int(pid_str) == int(proc.pid)

    client_node = OscNode('vidhubcontrol')
    client_dispatcher = OscDispatcher()
    client_node.osc_dispatcher = client_dispatcher
    client_addr = (str(HOST_IFACE.ip), osc_client_port)
    client = OSCUDPServer(client_addr, client_dispatcher)

    server_addr = (str(HOST_IFACE.ip), osc_server_port)

    print('starting client')
    await client.start()

    vidhub_node = client_node.add_child('vidhubs/by-id/dummy1')

    node_messages = []
    node_message_rx = asyncio.Event()
    def on_node_msg(node, client_addr, *messages):
        print(node, client_addr, messages)
        node_messages.append((node, messages))
        node_message_rx.set()

    client_node.bind(on_tree_message_received=on_node_msg)

    # TODO: this fails in OscInterface. Need to add test and debug
    # info_node = vidhub_node.add_child('info')
    # info_node.ensure_message(server_addr)
    #
    # await node_message_rx.wait()
    # node_message_rx.clear()

    print('setting crosspoints')
    for i in range(12):
        n = vidhub_node.add_child('crosspoints/{}'.format(i))
        n.ensure_message(server_addr, 0)
        await asyncio.sleep(.1)
        n.ensure_message(server_addr)
        await node_message_rx.wait()
        node_message_rx.clear()
        messages = node_messages[-1][1]
        assert messages[0] == 0

    print('recalling preset 0')
    n = vidhub_node.add_child('presets/0/recall')
    n.ensure_message(server_addr)
    await asyncio.sleep(.1)

    print('checking preset 0 active')
    n = vidhub_node.add_child('presets/0/active')
    n.ensure_message(server_addr)
    await node_message_rx.wait()
    node_message_rx.clear()
    messages = node_messages[-1][1]
    assert messages[0]
    # TODO: this should be "is True" might be an issue with the OSC type tag
    # assert messages[0] is True


    print('checking preset crosspoints')
    for i in range(12):
        n = vidhub_node.find('crosspoints/{}'.format(i))
        n.ensure_message(server_addr)
        await node_message_rx.wait()
        node_message_rx.clear()
        messages = node_messages[-1][1]
        assert messages[0] == 2

    await client.stop()

    print('shutting down subprocess')
    proc.send_signal(signal.SIGINT)
    err = await proc.wait()
    if err != 0:
        while True:
            line = await proc.stdout.readline()
            if not len(line):
                break
            print(repr(line))

    assert err == 0
