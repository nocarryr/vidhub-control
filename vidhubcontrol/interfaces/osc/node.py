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
    def build_osc_address(self):
        path = self.name
        p = self.parent
        if p is None:
            return '/{}'.format(path)
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
                tail = child.add_child(name, **kwargs)
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
    def ensure_message(self, client_address, *args, **kwargs):
        asyncio.ensure_future(self.send_message(client_address, *args, **kwargs))
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
