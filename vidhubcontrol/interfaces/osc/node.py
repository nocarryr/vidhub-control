import asyncio

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty, ListProperty

class OscNode(Dispatcher):
    name = Property()
    osc_address = Property()
    parent = Property()
    children = DictProperty()
    osc_dispatcher = Property()
    _events_ = ['on_message_received', 'on_tree_message_received']
    def __init__(self, name, parent=None, **kwargs):
        self.name = name
        self.bind(
            parent=self.on_parent,
            osc_dispatcher=self.on_osc_dispatcher,
        )
        self.parent = parent
        if self.parent is None:
            self.osc_address = self.build_osc_address()
            self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        else:
            self.event_loop = self.parent.event_loop
        osc_dispatcher = kwargs.get('osc_dispatcher')
        if osc_dispatcher is None:
            if self.parent is not None:
                osc_dispatcher = self.parent.osc_dispatcher
        self.osc_dispatcher = osc_dispatcher
        for ch_name, ckwargs in kwargs.get('children', {}).items():
            self.add_child(ch_name, **ckwargs)
    @classmethod
    def create_from_address(cls, osc_address, parent=None, **kwargs):
        name = osc_address.split('/')[0]
        child_address = '/'.join(osc_address.split('/')[1:])
        if len(child_address):
            if 'children' not in kwargs:
                kwargs['children'] = {}
            kwargs['children'][child_address] = {}
        root = cls(name, parent, **kwargs)
        return root, root.find(child_address)
    @property
    def root(self):
        p = self.parent
        if p is None:
            return self
        return p.root
    def find(self, osc_address):
        if osc_address.startswith('/'):
            return self.root.find(osc_address.lstrip('/'))
        if '/' not in osc_address:
            return self.children.get(osc_address)
        name = osc_address.split('/')[0]
        child = self.children.get(name)
        if child is not None:
            return child.find('/'.join(osc_address.split('/')[1:]))
    def build_osc_address(self, to_parent=None):
        path = self.name
        p = self.parent
        if p is to_parent:
            if to_parent is not None:
                return path
            else:
                return '/{}'.format(path)
        if to_parent is not None:
            return '/'.join([p.build_osc_address(to_parent), self.name])
        if p.osc_address is None:
            return None
        return '/'.join([p.osc_address, self.name])
    def add_child(self, name, node=None, cls=None, **kwargs):
        if cls is None:
            cls = OscNode
        if isinstance(node, OscNode):
            node.parent = self
            node.osc_dispatcher = self.osc_dispatcher
            child = tail = node
        elif '/' in name:
            if name.startswith('/'):
                return self.root.add_child(name.lstrip('/'), node, cls, **kwargs)
            tail = self.find(name)
            if tail is not None:
                return tail
            if name.split('/')[0] in self.children:
                child = self.children[name.split('/')[0]]
                name = '/'.join(name.split('/')[1:])
                tail = child.add_child(name, cls=cls, **kwargs)
            else:
                child, tail = self.create_from_address(name, self, **kwargs)
        else:
            if name in self.children:
                return self.children[name]
            child = cls(name, self, **kwargs)
            tail = child
        child.bind(on_tree_message_received=self.on_child_message_received)
        self.children[child.name] = child
        return tail
    def on_parent(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        self.osc_address = self.build_osc_address()
        if self.parent is not None:
            self.parent.bind(osc_address=self.on_parent_osc_address)
    def on_parent_osc_address(self, instance, value, **kwargs):
        if value is None:
            self.osc_address = None
        else:
            self.osc_address = self.build_osc_address()
    def on_osc_dispatcher(self, instance, obj, **kwargs):
        if obj is None:
            return
        obj.map(self.osc_address, self.on_osc_dispatcher_message)
        for child in self:
            child.osc_dispatcher = obj
    def ensure_message(self, client_address, *args, **kwargs):
        asyncio.ensure_future(
            self.send_message(client_address, *args, **kwargs),
            loop=self.event_loop,
        )
    async def send_message(self, client_address, *args, **kwargs):
        await self.osc_dispatcher.send_message(self, client_address, *args, **kwargs)
    def on_osc_dispatcher_message(self, osc_address, client_address, *messages):
        self.emit('on_message_received', self, client_address, *messages)
        self.emit('on_tree_message_received', self, client_address, *messages)
    def on_child_message_received(self, node, client_address, *messages):
        self.emit('on_tree_message_received', node, client_address, *messages)
    def __iter__(self):
        yield from self.children.values()
    def walk(self):
        yield self
        for child in self:
            yield from child.walk()
    def __repr__(self):
        return '<{self.__class__.__name__}>: {self}'.format(self=self)
    def __str__(self):
        return str(self.osc_address)

class PubSubOscNode(OscNode):
    # spec: tuple of (instance, property_name)
    published_property = Property()
    def __init__(self, name, parent=None, **kwargs):
        super().__init__(name, parent, **kwargs)
        self._subscriber_lock = asyncio.Lock()
        self.subscribers = set()
        subscribe_node = self.add_child('_subscribe')
        query_node = self.add_child('_query')
        list_node = self.add_child('_list')
        subscribe_node.bind(on_message_received=self.on_subscribe_node_message)
        query_node.bind(on_message_received=self.on_query_node_message)
        list_node.bind(on_message_received=self.on_list_node_message)
        self.bind(published_property=self.on_published_property)
        self.published_property = kwargs.get('published_property')
    def on_subscribe_node_message(self, node, client_address, *messages):
        if len(messages) == 1 and not messages[0]:
            remove = True
        else:
            remove = False
        asyncio.ensure_future(
            self._add_or_remove_subscriber(client_address, remove),
            loop=self.event_loop,
        )
    async def _add_or_remove_subscriber(self, client_address, remove):
        async with self._subscriber_lock:
            if remove:
                self.subscribers.discard(client_address)
            else:
                self.subscribers.add(client_address)
        node = self.find('_subscribe')
        await node.send_message(client_address)
    async def _send_to_subscribers(self, *messages):
        async with self._subscriber_lock:
            for client_address in self.subscribers:
                await self.send_message(client_address, *messages)
    def update_subscribers(self, *messages):
        asyncio.ensure_future(self._send_to_subscribers(*messages), loop=self.event_loop)
    def on_query_node_message(self, node, client_address, *messages):
        recursive = False
        if len(messages) and isinstance(messages[0], str):
            recursive = 'recursive' in messages[0].lower()
        if recursive:
            for node in self.walk():
                if not isinstance(node, PubSubOscNode):
                    continue
                try:
                    response = node.get_query_response()
                except NotImplementedError:
                    continue
                node.ensure_message(client_address, *response)
        else:
            try:
                response = self.get_query_response()
            except NotImplementedError:
                response = None
            self.ensure_message(client_address, *response)
    def get_query_response(self):
        prop = self.published_property
        if prop is not None:
            inst, prop = prop
            value = getattr(inst, prop)
            if isinstance(value, dict):
                value = value.keys()
            elif not isinstance(value, (list, tuple, set)):
                value = [value]
            return value
        raise NotImplementedError()
    def on_list_node_message(self, node, client_address, *messages):
        recursive = False
        if len(messages) and isinstance(messages[0], str):
            recursive = 'recursive' in messages[0].lower()
        if recursive:
            child_iter = self.walk()
        else:
            child_iter = self.children.values()
        child_iter = (n for n in child_iter if n.name not in ('_query', '_subscribe', '_list'))
        addrs = [n.build_osc_address(to_parent=self) for n in child_iter if n is not self]
        node = self.find('_list')
        node.ensure_message(client_address, *addrs)
    def on_published_property(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old_inst, old_prop = old
            old_inst.unbind(self.on_published_property_change)
        if value is None:
            return
        inst, prop = value
        inst.bind(**{prop:self.on_published_property_change})
    def on_published_property_change(self, instance, value, **kwargs):
        if isinstance(value, list):
            args = value
        elif isinstance(value, dict):
            args = value.keys()
        else:
            args = [value]
        self.update_subscribers(*args)
