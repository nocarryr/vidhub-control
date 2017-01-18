import asyncio
import ipaddress
import netifaces

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty

from vidhubcontrol.interfaces.osc.node import OscNode
from vidhubcontrol.interfaces.osc.server import OSCUDPServer, OscDispatcher

def find_ip_addresses(iface_name=None):
    if iface_name is not None:
        iface_names = [iface_name]
    else:
        iface_names = netifaces.interfaces()
    for iface_name in iface_names:
        addrs = netifaces.ifaddresses(iface_name)[netifaces.AF_INET]
        for addr in addrs:
            iface = ipaddress.IPv4Interface('/'.join([addr['addr'], addr['netmask']]))
            if iface.is_loopback:
                continue
            if iface.is_reserved:
                continue
            yield iface_name, iface


class OscInterface(Dispatcher):
    osc_dispatcher = Property()
    root_node = Property()
    iface_name = Property()
    hostport = Property(9000)
    hostiface = Property()
    vidhubs = DictProperty(copy_on_change=True)
    def __init__(self, **kwargs):
        self.iface_name = kwargs.get('iface_name')
        self.hostport = kwargs.get('hostport', 9000)
        hostaddr = kwargs.get('hostaddr')
        if self.iface_name is not None:
            for iface_name, iface in find_ip_addresses(self.hostiface):
                self.hostiface = iface
                break
        if self.hostiface is None:
            for iface_name, iface in find_ip_addresses():
                if hostaddr is not None and str(iface.ip) != hostaddr:
                    continue
                self.hostiface = iface
                self.iface_name = iface_name
        self.osc_dispatcher = OscDispatcher()
        self.server = None
        self.root_node = OscNode('vidhubcontrol', osc_dispatcher=self.osc_dispatcher)
        self.root_node.add_child('/vidhubs/by-id')
        self.root_node.add_child('/vidhubs/by-name')
        # self.root_node.add_child('vidhubs/_update')
        # subscribe_node = self.root_node.add_child('vidhubs/_subscribe')
        # query_node = self.root_node.add_child('vidhubs/_query')
        # query_node.bind(on_message_received=self.on_vidhub_query_message)
    async def add_vidhub(self, vidhub):
        await vidhub.connect_fut
        if vidhub.device_id in self.vidhubs:
            return
        node = VidhubNode(vidhub, use_device_id=True)
        self.root_node.find('vidhubs/by-id').add_child('', node)
        node.osc_dispatcher = self.osc_dispatcher
        node = VidhubNode(vidhub, use_device_id=False)
        self.root_node.find('vidhubs/by-name').add_child('', node)
        node.osc_dispatcher = self.osc_dispatcher
    async def start(self):
        if self.server is not None:
            await self.server.stop()
        addr = (str(self.hostiface.ip), self.hostport)
        self.server = OSCUDPServer(addr, self.osc_dispatcher)
        await self.server.start()
    async def stop(self):
        if self.server is not None:
            await self.server.stop()
        self.server = None

class VidhubNode(OscNode):
    _info_properties = [
        ('device_id', 'id'),
        ('device_name', 'name'),
        ('device_model', 'model'),
        ('device_version', 'version'),
        ('num_outputs', 'num_outputs'),
        ('num_inputs', 'num_inputs'),
    ]
    def __init__(self, vidhub, use_device_id=True):
        self.vidhub = vidhub
        self.use_device_id = use_device_id
        if use_device_id:
            name = self.vidhub.device_id
        else:
            name = self.vidhub.device_name
        super().__init__(name)
        info_children = {key:{} for __, key in self._info_properties}
        self.info_node = self.add_child('info', children=info_children)
        self.label_node = self.add_child('labels')
        self.label_node.add_child('input', cls=VidhubLabelNode, vidhub=vidhub)
        self.label_node.add_child('output', cls=VidhubLabelNode, vidhub=vidhub)
        self.crosspoint_node = self.add_child('crosspoints', cls=VidhubCrosspointNode, vidhub=vidhub)
    def get_device_info(self):
        d = {}
        for vidhub_attr, key in self._info_properties:
            d[key] = getattr(self.vidhub, attr)
        return d
    def on_child_message_received(self, node, client_address, *messages):
        if node is self.info_node:
            d = self.get_device_info()
            for key, val in d.items():
                node.children[key].ensure_message(client_address, val)
        super().on_child_message_received(self, node, client_address, *messages)

class VidhubLabelNode(OscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.vidhub = kwargs.get('vidhub')
        property_attr = '_'.join([self.name, 'labels'])
        self.vidhub_property = getattr(self.vidhub, property_attr)
        for i, lbl in enumerate(self.vidhub_property):
            node = self.add_child(str(i))
        #self.vidhub.bind(**{property_attr:self.on_vidhub_labels})
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        if not len(messages):
            lbls = self.vidhub_property[:]
            self.ensure_message(client_address, *lbls)
        elif len(messages) <= len(self.vidhub_property):
            for i, arg in enumerate(messages):
                self.vidhub_property[i] = arg
            lbls = self.vidhub_property[:]
            self.ensure_message(client_address, *lbls)
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)
    def on_child_message_received(self, node, client_address, *messages):
        i = int(node.name)
        if not len(messages):
            node.ensure_message(client_address, self.vidhub_property[i])
        else:
            lbl = messages[0]
            self.vidhub_property[i] = lbl
            node.ensure_message(client_address, self.vidhub_property[i])
        super().on_child_message_received(self, node, client_address, *messages)

class VidhubCrosspointNode(OscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.vidhub = kwargs.get('vidhub')
        for i in range(self.vidhub.num_outputs):
            self.add_child(name=str(i))
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        if not len(messages):
            self.ensure_message(client_address, self.vidhub.crosspoints[:])
        elif len(messages) <= len(self.vidhub.crosspoints):
            args = ((out_idx, in_idx) for out_idx, in_idx in enumerate(messages))
            asyncio.ensure_future(self.vidhub.set_crosspoints(*args))
            ## TODO: give feedback from async call
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)
    def on_child_message_received(self, node, client_address, *messages):
        i = int(node.name)
        if not len(messages):
            node.ensure_message(client_address, self.vidhub.crosspoints[i])
        else:
            asyncio.ensure_future(self.vidhub.set_crosspoint(i, messages[0]))
            #node.ensure_message(client_address, self.vidhub.crosspoints[i])
        super().on_child_message_received(self, node, client_address, *messages)
