import asyncio
import pytest

@pytest.mark.asyncio
async def test_nodes():
    from vidhubcontrol.interfaces.osc.node import OscNode

    class Listener(object):
        def __init__(self):
            self.messages_received = {}
            self.tree_messages_received = {}
        def on_message_received(self, node, client_address, *messages):
            if node.osc_address not in self.messages_received:
                self.messages_received[node.osc_address] = []
            self.messages_received[node.osc_address].extend([m for m in messages])
        def on_tree_message_received(self, node, client_address, *messages):
            if node.osc_address not in self.tree_messages_received:
                self.tree_messages_received[node.osc_address] = []
            self.tree_messages_received[node.osc_address].extend([m for m in messages])

    root = OscNode('root')
    assert root.osc_address == '/root'
    branchA = root.add_child('branchA', children={'leaf1':{}, 'leaf2':{}})
    assert branchA.parent == root
    assert branchA.osc_address == '/root/branchA'

    leafA1 = root.find('branchA/leaf1')
    leafA2 = root.find('branchA/leaf2')

    leafB1 = root.add_child('branchB/leaf1')
    branchB = leafB1.parent
    leafB2 = branchB.add_child('leaf2')

    assert leafB1.parent == leafB2.parent == branchB
    assert branchB.parent == root
    assert branchB.osc_address == '/root/branchB'
    assert leafB1.osc_address == '/root/branchB/leaf1'
    assert root.find('branchB/leaf1') == leafB1
    assert root.find('branchB/leaf2') == leafB2

    # root.add_child('branchC')
    # root.find('branchC').add_child('leaf1')
    # root.find('branchC').add_child('leaf2')
    leafC1 = root.add_child('branchC/leaf1')
    leafC2 = root.add_child('branchC/leaf2')
    print(repr(leafC1))
    print(repr(leafC2))

    all_nodes = {n.osc_address:n for n in root.walk()}
    print(all_nodes.keys())
    expected = {
        '/root',
        '/root/branchA',
        '/root/branchA/leaf1',
        '/root/branchA/leaf2',
        '/root/branchB',
        '/root/branchB/leaf1',
        '/root/branchB/leaf2',
        '/root/branchC',
        '/root/branchC/leaf1',
        '/root/branchC/leaf2',
    }
    assert set(all_nodes.keys()) == expected

    listener = Listener()

    for node in all_nodes.values():
        node.bind(on_message_received=listener.on_message_received)

    root.bind(on_tree_message_received=listener.on_tree_message_received)

    for node in all_nodes.values():
        node.on_osc_dispatcher_message(node.osc_address, None, *['foo', 'bar'])

    assert set(listener.messages_received.keys()) == set(all_nodes.keys())
    assert set(listener.tree_messages_received.keys()) == set(all_nodes.keys())
    for key in all_nodes.keys():
        assert listener.messages_received[key] == ['foo', 'bar']
        assert listener.tree_messages_received[key] == ['foo', 'bar']

@pytest.mark.asyncio
async def test_interface():
    from vidhubcontrol.interfaces.osc.node import OscNode
    from vidhubcontrol.interfaces.osc.interface import OscInterface
    from vidhubcontrol.interfaces.osc.server import OSCUDPServer, OscDispatcher
    from vidhubcontrol.backends.dummy import DummyBackend

    interface = OscInterface()
    vidhub = DummyBackend(device_name='dummy-name')
    await interface.add_vidhub(vidhub)
    await interface.start()

    client_node = OscNode('vidhubcontrol')
    client_dispatcher = OscDispatcher()
    client_node.osc_dispatcher = client_dispatcher
    client_addr = (str(interface.hostiface.ip), interface.hostport+1)
    client = OSCUDPServer(client_addr, client_dispatcher)

    await client.start()

    server_addr = interface.server._server_address

    assert interface.root_node.find('vidhubs/by-id/dummy') is not None
    assert interface.root_node.find('vidhubs/by-name/dummy-name') is not None

    for i, lbl in enumerate(vidhub.output_labels):
        addr = 'vidhubs/by-id/dummy/labels/output/{}'.format(i)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        cnode.ensure_message(server_addr, 'FOO OUT {}'.format(i))
        assert interface.root_node.find('vidhubs/by-name/dummy-name/labels/output/{}'.format(i)) is not None


    for i, lbl in enumerate(vidhub.input_labels):
        addr = 'vidhubs/by-id/dummy/labels/input/{}'.format(i)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        cnode.ensure_message(server_addr, 'FOO IN {}'.format(i))
        assert interface.root_node.find('vidhubs/by-name/dummy-name/labels/input/{}'.format(i)) is not None

    for out_idx, in_idx in enumerate(vidhub.crosspoints):
        addr = 'vidhubs/by-id/dummy/crosspoints/{}'.format(out_idx)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        cnode.ensure_message(server_addr, 2)
        assert interface.root_node.find('vidhubs/by-name/dummy-name/crosspoints/{}'.format(i)) is not None

    await asyncio.sleep(2)


    for i, lbl in enumerate(vidhub.output_labels):
        assert lbl == 'FOO OUT {}'.format(i)

    for i, lbl in enumerate(vidhub.input_labels):
        assert lbl == 'FOO IN {}'.format(i)

    for xpt in vidhub.crosspoints:
        assert xpt == 2


    # Test presets
    preset_node = client_node.add_child('vidhubs/by-id/dummy/presets')
    preset_node.add_child('recall')
    preset_node.add_child('store')
    crosspoint_node = client_node.find('vidhubs/by-id/dummy/crosspoints')

    class PresetAwait(object):
        def __init__(self, event_name):
            self.event = asyncio.Event()
            self.args = None
            self.kwargs = None
            vidhub.bind(**{event_name:self.on_vidhub_event})
        def on_vidhub_event(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.event.set()
        async def wait(self):
            await self.event.wait()
            self.event.clear()
            return self.args, self.kwargs

    waiter = PresetAwait('on_preset_stored')

    for i in range(vidhub.num_inputs):
        xpts = [i]*vidhub.num_outputs
        crosspoint_node.ensure_message(server_addr, *xpts)
        await asyncio.sleep(.2)
        assert vidhub.crosspoints == xpts
        name = 'preset_{}'.format(i)
        preset_node.find('store').ensure_message(server_addr, i, name)
        await waiter.wait()
        assert vidhub.presets[i].name == name
        assert vidhub.presets[i].crosspoints == {i:v for i, v in enumerate(xpts)}

    assert len(vidhub.presets) == vidhub.num_inputs

    waiter = PresetAwait('on_preset_active')

    for preset in vidhub.presets:
        assert not preset.active
        preset_node.find('recall').ensure_message(server_addr, preset.index)
        await waiter.wait()
        assert preset.active

    await client.stop()
    await interface.stop()
