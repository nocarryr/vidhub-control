
def test_nodes():
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

    all_nodes = {n.osc_address:n for n in root.walk()}
    expected = {
        '/root',
        '/root/branchA',
        '/root/branchA/leaf1',
        '/root/branchA/leaf2',
        '/root/branchB',
        '/root/branchB/leaf1',
        '/root/branchB/leaf2',
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
