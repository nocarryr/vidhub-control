import asyncio
import pytest
from utils import get_random_values

@pytest.mark.asyncio
async def test_nodes():
    from vidhubcontrol.interfaces.osc import OscNode

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
async def test_pubsub_nodes(missing_netifaces, unused_tcp_port_factory):
    from pydispatch import Dispatcher, Property
    from vidhubcontrol.interfaces.osc import OscNode, PubSubOscNode, OSCUDPServer, OscDispatcher

    server_port, client_port = unused_tcp_port_factory(), unused_tcp_port_factory()

    class Publisher(Dispatcher):
        value = Property()
        other_value = Property()
        def __init__(self, root_node, osc_address):
            self.osc_address = osc_address
            self.random_values = get_random_values(8)
            self.msg_queue = asyncio.Queue()
            if root_node.osc_address == osc_address:
                self.osc_node = root_node
            else:
                self.osc_node = root_node.add_child(osc_address)
            self.subscribe_node = self.osc_node.add_child('_subscribe')
            self.query_node = self.osc_node.add_child('_query')
            self.list_node = self.osc_node.add_child('_list')
            for node in [self.osc_node, self.subscribe_node, self.query_node, self.list_node]:
                node.bind(on_message_received=self.on_client_node_message)
        async def wait_for_response(self):
            msg = await asyncio.wait_for(self.msg_queue.get(), timeout=5)
            self.msg_queue.task_done()
            return msg
        async def subscribe(self, server_addr):
            await self.subscribe_node.send_message(server_addr)
            msg = await self.wait_for_response()
            return msg
        async def query(self, server_addr, recursive=False):
            if recursive:
                await self.query_node.send_message(server_addr, 'recursive')
            else:
                await self.query_node.send_message(server_addr)
            msg = await self.wait_for_response()
            return msg
        def on_client_node_message(self, node, client_address, *messages):
            print('on_client_node_message: ', node, messages)
            self.msg_queue.put_nowait({
                'node':node,
                'client_address':client_address,
                'messages':messages,
            })

    node_addresses = [
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
    ]

    listeners = {}

    publish_root = PubSubOscNode('root')
    subscribe_root = OscNode('root')

    listener = Publisher(subscribe_root, subscribe_root.osc_address)
    listeners[listener.osc_node.osc_address] = listener

    for addr in node_addresses:
        if addr == '/root':
            pub_node = publish_root
        else:
            _addr = addr.lstrip('/root/')
            listener = Publisher(subscribe_root, _addr)
            listeners[listener.osc_node.osc_address] = listener
            pub_node = publish_root.add_child(_addr, cls=PubSubOscNode, published_property=(listener, 'value'))
            assert listener.osc_node.osc_address == addr

    assert set(node_addresses) == set(listeners.keys())

    pub_addrs = set((n.osc_address for n in publish_root.walk()))
    sub_addrs = set((n.osc_address for n in subscribe_root.walk()))
    assert pub_addrs == sub_addrs

    server_addr = ('127.0.0.1', server_port)
    server_dispatcher = OscDispatcher()
    publish_root.osc_dispatcher = server_dispatcher
    server = OSCUDPServer(server_addr, server_dispatcher)

    client_addr = ('127.0.0.1', client_port)
    client_dispatcher = OscDispatcher()
    subscribe_root.osc_dispatcher = client_dispatcher
    client = OSCUDPServer(client_addr, client_dispatcher)

    await server.start()
    await client.start()

    # Subscribe and test for property changes and query responses
    for listener in listeners.values():
        if listener.osc_node is subscribe_root:
            continue
        msg = await listener.subscribe(server_addr)
        assert msg['node'] is listener.subscribe_node
        for v in listener.random_values:
            listener.value = v
            msg = await listener.wait_for_response()
            assert msg['node'] is listener.osc_node
            assert len(msg['messages']) == 1
            if isinstance(v, float):
                assert v == pytest.approx(msg['messages'][0])
            else:
                assert v == msg['messages'][0]
        msg = await listener.query(server_addr)
        assert msg['node'] is listener.osc_node
        assert len(msg['messages']) == 1
        if isinstance(v, float):
            assert listener.value == pytest.approx(msg['messages'][0])
        else:
            assert listener.value == msg['messages'][0]

    listener = listeners['/root']

    # published_property has not yet been set on the root node
    # so there should be no responses
    with pytest.raises(NotImplementedError):
        publish_root.get_query_response()
        publish_root.on_query_node_message(publish_root, client_address)

    await listener.query_node.send_message(server_addr)
    await asyncio.sleep(1)
    assert listener.msg_queue.empty()

    # Set the property value to something other than None to avoid
    # errors in python-osc
    listener.value = 'a'

    # Now test binding post-init
    publish_root.published_property = (listener, 'value')
    msg = await listener.query(server_addr)
    assert msg['node'] is listener.osc_node
    assert len(msg['messages']) == 1
    assert msg['messages'][0] == listener.value == 'a'

    msg = await listener.subscribe(server_addr)
    assert msg['node'] is listener.subscribe_node
    listener.value = 'foo'
    msg = await listener.wait_for_response()
    assert msg['node'] is listener.osc_node
    assert len(msg['messages']) == 1
    assert msg['messages'][0] == listener.value == 'foo'

    msg = await listener.query(server_addr, recursive=True)
    assert msg['node'] is listener.osc_node
    assert len(msg['messages']) == 1
    assert msg['messages'][0] == listener.value

    for _listener in listeners.values():
        if _listener is listener:
            continue
        msg = await _listener.wait_for_response()
        assert msg['node'] is _listener.osc_node
        assert len(msg['messages']) == 1
        if isinstance(_listener.value, float):
            assert msg['messages'][0] == pytest.approx(_listener.value)
        else:
            assert msg['messages'][0] == _listener.value

    # Test property re-binding
    for _listener in listeners.values():
        current_value = _listener.value
        if _listener.osc_node is subscribe_root:
            pub_node = publish_root
        else:
            pub_node = publish_root.find(_listener.osc_address.lstrip('/root/'))
        pub_node.published_property = (_listener, 'other_value')
        _listener.value = 'foobar'
        _listener.other_value = 'baz'
        msg = await _listener.wait_for_response()
        assert len(msg['messages']) == 1
        assert msg['messages'][0] == _listener.other_value == 'baz'
        pub_node.published_property = (_listener, 'value')
        _listener.value = current_value
        msg = await _listener.wait_for_response()
        assert len(msg['messages']) == 1
        if isinstance(current_value, float):
            assert pytest.approx(msg['messages'][0]) == _listener.value == current_value
        else:
            assert msg['messages'][0] == _listener.value == current_value
        assert _listener.msg_queue.empty()

    # Unbind published_property and test for recursive empty responses
    for _listener in listeners.values():
        if _listener.osc_node is subscribe_root:
            pub_node = publish_root
        else:
            pub_node = publish_root.find(_listener.osc_address.lstrip('/root/'))
        pub_node.published_property = None

    await listener.query_node.send_message(server_addr, 'recursive')
    await asyncio.sleep(1)
    for _listener in listeners.values():
        assert _listener.msg_queue.empty()


    # Test list (recursive and non-recursive)
    await listener.list_node.send_message(server_addr, False)
    msg = await listener.wait_for_response()
    assert msg['node'] is listener.list_node
    expected = ['branchA', 'branchB', 'branchC']
    assert set(msg['messages']) == set(expected)

    await listener.list_node.send_message(server_addr, 'recursive')
    msg = await listener.wait_for_response()
    assert msg['node'] is listener.list_node
    expected = [addr.lstrip('/root/') for addr in node_addresses if addr != '/root']
    assert set(msg['messages']) == set(expected)


    await client.stop()
    await server.stop()

@pytest.mark.asyncio
async def test_interface(missing_netifaces, unused_tcp_port_factory):
    from vidhubcontrol.interfaces.osc import OscNode, OscInterface, OSCUDPServer, OscDispatcher
    from vidhubcontrol.backends import DummyBackend

    server_port, client_port = unused_tcp_port_factory(), unused_tcp_port_factory()

    class NodeResponse(object):
        def __init__(self, node=None):
            self.msg_queue = asyncio.Queue()
            self.node = node
        @property
        def node(self):
            return getattr(self, '_node', None)
        @node.setter
        def node(self, node):
            if self.node is not None:
                self.node.unbind(self)
            self._node = node
            print(node)
            if node is not None:
                node.bind(on_message_received=self.on_message_received)
        async def subscribe_to_node(self, node, server_addr):
            self.node = None
            subscribe_node = node.add_child('_subscribe')
            self.node = subscribe_node
            await subscribe_node.send_message(server_addr)
            await self.wait_for_response()
            self.node = node
        async def unsubscribe(self, server_addr):
            subscribe_node = self.node.find('_subscribe')
            self.node = subscribe_node
            await subscribe_node.send_message(server_addr, False)
            await self.wait_for_response()
            self.node = None
        async def wait_for_response(self):
            msg = await asyncio.wait_for(self.msg_queue.get(), timeout=5)
            self.msg_queue.task_done()
            return msg
        def on_message_received(self, node, client_address, *messages):
            print('on_message_received: ', node, client_address, messages)
            self.msg_queue.put_nowait({
                'node':node,
                'client_address':client_address,
                'messages':messages,
            })

    interface = OscInterface(hostport=server_port)
    vidhub = DummyBackend(device_name='dummy-name')
    await interface.add_vidhub(vidhub)
    await interface.start()

    client_node = OscNode('vidhubcontrol')
    client_dispatcher = OscDispatcher()
    client_node.osc_dispatcher = client_dispatcher
    client_addr = (str(interface.hostiface.ip), client_port)
    client = OSCUDPServer(client_addr, client_dispatcher)

    await client.start()

    server_addr = interface.server._server_address

    assert interface.root_node.find('vidhubs/by-id/dummy') is not None
    assert interface.root_node.find('vidhubs/by-name/dummy-name') is not None

    by_id_response = NodeResponse()
    n = client_node.add_child('vidhubs/by-id')
    await by_id_response.subscribe_to_node(n, server_addr)
    n = n.add_child('_query')
    await n.send_message(server_addr)
    msg = await by_id_response.wait_for_response()
    assert vidhub.device_id in msg['messages']

    by_name_response = NodeResponse()
    await by_name_response.subscribe_to_node(client_node.add_child('vidhubs/by-name'), server_addr)

    cnode = client_node.add_child('vidhubs/by-id/dummy/labels/output/_list')
    node_response = NodeResponse(cnode)
    await cnode.send_message(server_addr)
    msg = await node_response.wait_for_response()
    assert set(msg['messages']) == set((str(i) for i in range(vidhub.num_outputs)))

    for i, lbl in enumerate(vidhub.output_labels):
        addr = 'vidhubs/by-id/dummy/labels/output/{}'.format(i)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        await node_response.subscribe_to_node(cnode, server_addr)
        await cnode.send_message(server_addr, 'FOO OUT {}'.format(i))
        msg = await node_response.wait_for_response()
        assert msg['messages'][0] == 'FOO OUT {}'.format(i)
        assert interface.root_node.find('vidhubs/by-name/dummy-name/labels/output/{}'.format(i)) is not None
        await node_response.unsubscribe(server_addr)


    for i, lbl in enumerate(vidhub.input_labels):
        addr = 'vidhubs/by-id/dummy/labels/input/{}'.format(i)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        await node_response.subscribe_to_node(cnode, server_addr)
        await cnode.send_message(server_addr, 'FOO IN {}'.format(i))
        msg = await node_response.wait_for_response()
        assert msg['messages'][0] == 'FOO IN {}'.format(i)
        assert interface.root_node.find('vidhubs/by-name/dummy-name/labels/input/{}'.format(i)) is not None
        await node_response.unsubscribe(server_addr)

    crosspoint_node = client_node.add_child('vidhubs/by-id/dummy/crosspoints')
    crosspoint_response = NodeResponse()
    await crosspoint_response.subscribe_to_node(crosspoint_node, server_addr)
    await crosspoint_node.add_child('_query').send_message(server_addr)
    msg = await crosspoint_response.wait_for_response()
    assert list(msg['messages']) == vidhub.crosspoints[:]

    for out_idx, in_idx in enumerate(vidhub.crosspoints):
        addr = 'vidhubs/by-id/dummy/crosspoints/{}'.format(out_idx)
        assert interface.root_node.find(addr) is not None
        cnode = client_node.add_child(addr)
        await node_response.subscribe_to_node(cnode, server_addr)
        await cnode.send_message(server_addr, 2)
        msg = await node_response.wait_for_response()
        assert msg['node'].osc_address == cnode.osc_address
        assert msg['messages'][0] == 2
        assert interface.root_node.find('vidhubs/by-name/dummy-name/crosspoints/{}'.format(i)) is not None
        await node_response.unsubscribe(server_addr)

        msg = await crosspoint_response.wait_for_response()
        assert crosspoint_response.msg_queue.empty()
        assert list(msg['messages']) == vidhub.crosspoints[:]


    for i, lbl in enumerate(vidhub.output_labels):
        assert lbl == 'FOO OUT {}'.format(i)

    for i, lbl in enumerate(vidhub.input_labels):
        assert lbl == 'FOO IN {}'.format(i)

    for xpt in vidhub.crosspoints:
        assert xpt == 2

    expected = vidhub.crosspoints[:]
    await crosspoint_node.send_message(server_addr)
    msg = await crosspoint_response.wait_for_response()
    assert msg['node'].osc_address == crosspoint_node.osc_address
    assert list(msg['messages']) == expected

    expected = set(str(i) for i in range(vidhub.num_outputs))
    crosspoint_list_node = crosspoint_node.add_child('_list')
    node_response.node = crosspoint_list_node
    await crosspoint_list_node.send_message(server_addr)
    msg = await node_response.wait_for_response()
    assert msg['node'].osc_address == crosspoint_list_node.osc_address
    assert set(msg['messages']) == expected


    # Test presets
    preset_node = client_node.add_child('vidhubs/by-id/dummy/presets')
    preset_node.add_child('recall')
    preset_node.add_child('store')

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
            await asyncio.wait_for(self.event.wait(), timeout=5)
            self.event.clear()
            return self.args, self.kwargs

    waiter = PresetAwait('on_preset_stored')

    await node_response.subscribe_to_node(crosspoint_node, server_addr)

    preset_response = NodeResponse()

    for i in range(vidhub.num_inputs):
        xpts = [i]*vidhub.num_outputs
        await crosspoint_node.send_message(server_addr, *xpts)
        while True:
            msg = await node_response.wait_for_response()
            assert msg['node'].osc_address == crosspoint_node.osc_address
            if list(msg['messages']) == xpts:
                break
            await asyncio.sleep(0)
        msg = await crosspoint_response.wait_for_response()
        assert list(msg['messages']) == vidhub.crosspoints
        assert vidhub.crosspoints == xpts
        name = 'preset_{}'.format(i)
        preset_node.find('store').ensure_message(server_addr, i, name)
        await waiter.wait()
        assert vidhub.presets[i].name == name
        assert vidhub.presets[i].crosspoints == {i:v for i, v in enumerate(xpts)}

    assert len(vidhub.presets) == vidhub.num_inputs

    expected = set((str(p.index) for p in vidhub.presets))
    preset_response.node = preset_node
    await preset_node.send_message(server_addr)
    msg = await preset_response.wait_for_response()
    assert msg['node'].osc_address == preset_node.osc_address
    assert set(msg['messages']) == expected

    preset_list_node = preset_node.add_child('_list')
    preset_response.node = preset_list_node
    await preset_list_node.send_message(server_addr)
    msg = await preset_response.wait_for_response()
    assert msg['node'].osc_address == preset_list_node.osc_address
    expected |= set(['recall', 'store'])
    assert set(msg['messages']) == expected

    for preset in vidhub.presets:
        await preset_response.subscribe_to_node(
            preset_node.add_child('/'.join([str(preset.index), 'active'])),
            server_addr,
        )
        assert not preset.active
        n = preset_node.find('recall')
        await n.send_message(server_addr, preset.index)
        msg = await preset_response.wait_for_response()
        assert msg['node'].osc_address == preset_response.node.osc_address
        assert msg['messages'][0] == True
        assert preset.active

    vidhub.device_name = 'dummy-foo'
    msg = await by_name_response.wait_for_response()
    assert 'dummy-foo' in msg['messages']

    vidhub2 = DummyBackend(device_id='dummy2', device_name='dummy-name-2')
    await interface.add_vidhub(vidhub2)

    msg = await by_id_response.wait_for_response()
    assert set(msg['messages']) == set([vidhub.device_id, vidhub2.device_id])

    msg = await by_name_response.wait_for_response()
    assert set(msg['messages']) == set([vidhub.device_name, vidhub2.device_name])

    await client.stop()
    await interface.stop()

@pytest.mark.asyncio
async def test_interface_config(tempconfig, missing_netifaces):
    from vidhubcontrol.config import Config
    from vidhubcontrol.backends import DummyBackend
    from vidhubcontrol.interfaces.osc import OscInterface

    config = Config.load(str(tempconfig))
    interface = OscInterface(config=config)

    await config.start()
    await interface.start()

    vidhub = await DummyBackend.create_async(device_id='foo')
    await config.add_vidhub(vidhub)

    async def wait_for_foo():
        while 'foo' not in interface.vidhubs:
            await asyncio.sleep(.1)

    await asyncio.wait_for(wait_for_foo(), timeout=5)

    vidhub_node = interface.root_node.find('vidhubs/by-id/foo')

    for i in range(vidhub.num_outputs):
        assert vidhub_node.find('crosspoints/{}'.format(i)) is not None
        assert vidhub_node.find('labels/output/{}'.format(i)) is not None

    for i in range(vidhub.num_inputs):
        assert vidhub_node.find('labels/input/{}'.format(i)) is not None

    await interface.stop()
    await config.stop()
