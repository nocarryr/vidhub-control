import asyncio
import ipaddress

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty

from vidhubcontrol.utils import find_ip_addresses
from .node import OscNode, PubSubOscNode
from .server import OSCUDPServer, OscDispatcher


class OscInterface(Dispatcher):
    DEFAULT_HOSTPORT = 9000
    osc_dispatcher = Property()
    root_node = Property()
    iface_name = Property()
    hostport = Property(DEFAULT_HOSTPORT)
    hostiface = Property()
    config = Property()
    vidhubs = DictProperty(copy_on_change=True)
    vidhubs_by_name = DictProperty()
    def __init__(self, **kwargs):
        self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        self.bind(config=self.on_config)
        self.config = kwargs.get('config')
        self.iface_name = kwargs.get('iface_name')
        self.hostport = kwargs.get('hostport', 9000)
        hostaddr = kwargs.get('hostaddr')
        if self.iface_name is not None:
            for iface_name, iface in find_ip_addresses(self.hostiface):
                self.hostiface = iface
                break
        if self.hostiface is None:
            exclude_loopback=True
            if hostaddr is not None:
                hostaddr = ipaddress.ip_address(hostaddr)
                exclude_loopback=False
            for iface_name, iface in find_ip_addresses(exclude_loopback=exclude_loopback):
                if hostaddr is not None:
                    if hostaddr not in iface.network:
                        continue
                self.hostiface = iface
                self.iface_name = iface_name
        self.osc_dispatcher = OscDispatcher()
        self.server = None
        self.root_node = OscNode(
            'vidhubcontrol',
            osc_dispatcher=self.osc_dispatcher,
            event_loop=self.event_loop,
        )
        vidhub_node = self.root_node.add_child('vidhubs')
        vidhub_node.add_child(
            'by-id',
            cls=PubSubOscNode,
            published_property=(self, 'vidhubs'),
        )
        vidhub_node.add_child(
            'by-name',
            cls=PubSubOscNode,
            published_property=(self, 'vidhubs_by_name'),
        )
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
        self.vidhubs[vidhub.device_id] = vidhub
        self.vidhubs_by_name[vidhub.device_name] = vidhub
        vidhub.bind(device_name=self.on_vidhub_name)
    async def start(self):
        if self.server is not None:
            await self.server.stop()
        if self.config is not None:
            if not self.config.running.is_set():
                await self.config.start()
            if self.config.USE_DISCOVERY:
                await self.publish_zeroconf_service()
        addr = (str(self.hostiface.ip), self.hostport)
        self.server = OSCUDPServer(addr, self.osc_dispatcher)
        await self.server.start()
    async def stop(self):
        if self.server is not None:
            await self.server.stop()
        self.server = None
    async def publish_zeroconf_service(self):
        await self.config.discovery_listener.publish_service(
            '_osc._udp.local.', self.hostport, properties={
                'txtvers':'1',
                'version':'1.1',
                'types':'ifsbrTF',
            }
        )
    def on_vidhub_name(self, instance, value, **kwargs):
        old = kwargs.get('old')
        with self.emission_lock('vidhubs_by_name'):
            del self.vidhubs_by_name[old]
            self.vidhubs_by_name[value] = instance
    def on_config(self, instance, config, **kwargs):
        if config is None:
            return
        self.update_config_vidhubs()
        config.bind(vidhubs=self.update_config_vidhubs)
    def update_config_vidhubs(self, *args, **kwargs):
        for vidhub_conf in self.config.vidhubs.values():
            if vidhub_conf.device_id is None:
                continue
            vidhub = vidhub_conf.backend
            asyncio.ensure_future(self.add_vidhub(vidhub), loop=self.event_loop)


class VidhubNode(PubSubOscNode):
    _info_properties = [
        ('device_id', 'id'),
        ('device_name', 'name'),
        ('device_model', 'model'),
        ('device_version', 'version'),
        ('num_outputs', 'num_outputs'),
        ('num_inputs', 'num_inputs'),
    ]
    device_info = DictProperty()
    def __init__(self, vidhub, use_device_id=True):
        self.vidhub = vidhub
        self.use_device_id = use_device_id
        if use_device_id:
            name = self.vidhub.device_id
        else:
            name = self.vidhub.device_name
        super().__init__(name)
        info_node = self.add_child('info', cls=PubSubOscNode)
        for vidhub_attr, name in self._info_properties:
            info_node.add_child(
                name,
                cls=VidhubInfoNode,
                published_property=(self.vidhub, vidhub_attr),
            )
        self.label_node = self.add_child('labels', cls=PubSubOscNode)
        self.label_node.add_child('input', cls=VidhubLabelNode, vidhub=vidhub)
        self.label_node.add_child('output', cls=VidhubLabelNode, vidhub=vidhub)
        self.crosspoint_node = self.add_child('crosspoints', cls=VidhubCrosspointNode, vidhub=vidhub)
        self.preset_node = self.add_child('presets', cls=VidhubPresetGroupNode, vidhub=vidhub)


class VidhubInfoNode(PubSubOscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)
        if self.name != 'name':
            return
        if len(messages) == 1:
            vidhub, prop = self.published_property
            vidhub.device_name = messages[0]

class VidhubLabelNode(PubSubOscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.property_attr = '_'.join([self.name, 'labels'])
        self.vidhub_property = getattr(self.vidhub, self.property_attr)
        for i, lbl in enumerate(self.vidhub_property):
            node = self.add_child(str(i), cls=VidhubSingleLabelNode)
        self.published_property = (self.vidhub, self.property_attr)
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
        if node.name.isdigit():
            i = int(node.name)
            if not len(messages):
                node.ensure_message(client_address, self.vidhub_property[i])
            else:
                lbl = messages[0]
                self.vidhub_property[i] = lbl
                node.ensure_message(client_address, self.vidhub_property[i])
        super().on_child_message_received(node, client_address, *messages)

class VidhubSingleLabelNode(PubSubOscNode):
    value = Property()
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.index = int(name)
        self.published_property = (self, 'value')
        self.value = self.parent.vidhub_property[self.index]
        self.parent.vidhub.bind(**{self.parent.property_attr:self.on_vidhub_labels})
    def on_vidhub_labels(self, instance, value, **kwargs):
        self.value = value[self.index]

class VidhubCrosspointNode(PubSubOscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.vidhub = kwargs.get('vidhub')
        for i in range(self.vidhub.num_outputs):
            self.add_child(name=str(i), cls=VidhubSingleCrosspointNode, index=i)
        self.published_property = (self.vidhub, 'crosspoints')
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        if not len(messages):
            self.ensure_message(client_address, *self.vidhub.crosspoints[:])
        elif len(messages) <= len(self.vidhub.crosspoints):
            args = ((out_idx, in_idx) for out_idx, in_idx in enumerate(messages))
            asyncio.ensure_future(
                self.vidhub.set_crosspoints(*args),
                loop=self.vidhub.event_loop,
            )
            ## TODO: give feedback from async call
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)

class VidhubSingleCrosspointNode(PubSubOscNode):
    index = Property()
    value = Property()
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.published_property = (self, 'value')
        self.index = kwargs.get('index')
        self.value = self.parent.vidhub.crosspoints[self.index]
        self.parent.vidhub.bind(crosspoints=self.on_crosspoints)
    def on_crosspoints(self, instance, value, **kwargs):
        self.value = value[self.index]
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        if not len(messages):
            self.ensure_message(client_address, self.value)
        else:
            xpt = messages[0]
            asyncio.ensure_future(
                self.parent.vidhub.set_crosspoint(self.index, xpt),
                loop=self.parent.vidhub.event_loop,
            )
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)

class VidhubPresetGroupNode(PubSubOscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.preset_nodes = {}
        self.add_child(name='recall')
        self.add_child(name='store')
        self.build_preset_nodes()
        self.vidhub.bind(presets=self.build_preset_nodes)
    def build_preset_nodes(self, *args, **kwargs):
        for preset in self.vidhub.presets:
            name = str(preset.index)
            if name in self.preset_nodes:
                continue
            self.add_child(name=name, cls=VidhubPresetNode, preset=preset)
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        if not len(messages):
            response = (str(preset.index) for preset in self.vidhub.presets)
            self.ensure_message(client_address, *response)
        super().on_osc_dispatcher_message(osc_address, client_address, *messages)
    def on_child_message_received(self, node, client_address, *messages):
        loop = self.vidhub.event_loop
        if node.name == 'recall':
            for i in messages:
                try:
                    preset = self.vidhub.presets[i]
                except IndexError:
                    continue
                asyncio.ensure_future(preset.recall(), loop=loop)
        elif node.name == 'store':
            # args:
            #       preset_index (int, optional)
            #       name (str, optional)
            #       outputs_to_store (*ints, optional)
            if not len(messages):
                asyncio.ensure_future(self.vidhub.store_preset(), loop=loop)
            else:
                i = messages[0]
                try:
                    name = messages[1]
                except IndexError:
                    name = None
                if len(messages) > 2:
                    outputs_to_store = messages[2:]
                else:
                    outputs_to_store = None
                asyncio.ensure_future(self.vidhub.store_preset(
                    outputs_to_store=outputs_to_store,
                    name=name,
                    index=i,
                ), loop=loop)
        super().on_child_message_received(node, client_address, *messages)

class VidhubPresetNode(PubSubOscNode):
    def __init__(self, name, parent, **kwargs):
        super().__init__(name, parent, **kwargs)
        self.preset = kwargs.get('preset')
        for name in ['name', 'active']:
            self.add_child(name, cls=PubSubOscNode, published_property=(self.preset, name))
        for name in ['recall', 'store']:
            self.add_child(name)
    def on_child_message_received(self, node, client_address, *messages):
        loop = self.preset.backend.event_loop
        if node.name == 'name':
            if not len(messages):
                node.ensure_message(client_address, self.preset.name)
            else:
                self.preset.name = messages[0]
        elif node.name == 'active':
            node.ensure_message(client_address, self.preset.active)
        elif node.name == 'recall':
            asyncio.ensure_future(self.preset.recall(), loop=loop)
        elif node.name == 'store':
            if not len(messages):
                outputs_to_store = None
            else:
                outputs_to_store = list(messages)
            asyncio.ensure_future(
                self.preset.store(outputs_to_store=outputs_to_store),
                loop=loop,
            )
        super().on_child_message_received(node, client_address, *messages)
