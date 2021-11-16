from loguru import logger
import asyncio
from typing import Optional, List, Dict, ClassVar

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

from vidhubcontrol.common import ConnectionState, ConnectionManager

class BackendBase(Dispatcher):
    """Base class for communicating with devices

    :Events:
        .. function:: on_preset_added(backend: BackendBase = self, preset: Preset = preset)

            This :class:`~pydispatch.dispatch.Event` is emitted
            when a new :class:`Preset` has been added.

        .. function:: on_preset_stored(backend: BackendBase = self, preset: Preset = preset)

            This :class:`~pydispatch.dispatch.Event` is emitted
            when an existing :class:`Preset` has been recorded (updated).

        .. function:: on_preset_active(backend: BackendBase, preset: Preset = preset, value: bool = value)

            This :class:`~pydispatch.dispatch.Event` is emitted
            when an existing :class:`Preset` has determined that its stored
            routing information is currently active on the switcher.

    """
    device_name: str = Property()

    device_model: str = Property()
    """The model name as reported by the device"""

    device_id: str = Property()
    """The unique id as reported by the device"""

    device_version: str = Property()
    """Firmware version reported by the device"""

    connection_manager: ConnectionManager
    """Manager for the device's :class:`~.common.ConnectionState`"""

    prelude_parsed: bool = Property(False)
    def __init__(self, **kwargs):
        self.connection_manager = ConnectionManager()
        self.device_name = kwargs.get('device_name')
        self.client = None
        self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        self.bind(device_id=self.on_device_id)
        if self.device_id is None:
            self.device_id = kwargs.get('device_id')
    @property
    def connection_state(self) -> ConnectionState:
        """The current :attr:`~.common.ConnectionManager.state` of the
        :attr:`connection_manager`
        """
        return self.connection_manager.state
    @classmethod
    async def create_async(cls, **kwargs):
        obj = cls(**kwargs)
        await obj.connect()
        return obj
    async def connect(self):
        manager = self.connection_manager
        async with manager:
            if manager.state & ConnectionState.waiting != 0:
                state = await manager.wait_for('connected|not_connected')
            if manager.state.is_connected:
                return self.client
            assert ConnectionState.not_connected in manager.state
            await manager.set_state('connecting')
        await asyncio.sleep(0)
        try:
            r = await asyncio.wait_for(self.do_connect(), timeout=2)
        except asyncio.TimeoutError as exc:
            r = False
        async with manager:
            if r is False and ConnectionState.failure not in manager.state:
                await manager.set_failure('unknown')
            if ConnectionState.failure in manager.state:
                await manager.set_state('not_connected')
            else:
                if self.client is not None:
                    self.client = r
                await manager.set_state('connected')
        return r
    async def disconnect(self):
        manager = self.connection_manager
        async with manager:
            if ConnectionState.not_connected in manager.state:
                return
            elif ConnectionState.disconnecting in manager.state:
                await manager.wait_for('not_connected')
                return
            elif ConnectionState.connecting in manager.state:
                state = await manager.wait_for('connected|not_connected')
                if state == ConnectionState.not_connected:
                    return
            assert manager.state.is_connected
            await manager.set_state('disconnecting')
        await asyncio.sleep(0)
        await self.do_disconnect()
        async with manager:
            self.client = None
            await manager.set_state('not_connected')
    async def _catch_exception(self, e: Exception, is_error: Optional[bool] = False):
        if not is_error:
            logger.exception(e)
            return
        exc_type = e.__class__
        try:
            exc_info = e.args
        except:
            exc_info = str(e)
        async with self.connection_manager as manager:
            await manager.set_failure(exc_info, e)
        try:
            await self.do_disconnect()
        finally:
            self.client = None
            async with self.connection_manager as manager:
                await manager.set_state('not_connected')
    async def do_connect(self):
        raise NotImplementedError()
    async def do_disconnect(self):
        raise NotImplementedError()
    async def get_status(self):
        raise NotImplementedError()
    def on_device_id(self, instance, value, **kwargs):
        if value is None:
            return
        if self.device_name is None:
            self.device_name = value
        self.unbind(self.on_device_id)

class VidhubBackendBase(BackendBase):
    """Base class for Videohub devices

    Attributes:
        num_outputs (int): The number of outputs as reported by the switcher.
        num_inputs (int): The number of inputs as reported by the switcher.
        crosspoints: This represents the currently active routing of the
            switcher. Each element in the ``list`` represents an output (the
            zero-based index of the ``list``) with its selected index as the
            value (also zero-based).
            This is a :class:`pydispatch.properties.ListProperty` and can be
            observed using the :meth:`~pydispatch.Dispatcher.bind` method.
        output_labels: A ``list`` containing the names of each output
            as reported by the switcher
            This is a :class:`pydispatch.properties.ListProperty` and can be
            observed using the :meth:`~pydispatch.Dispatcher.bind` method.
        input_labels: A ``list`` containing the names of each input
            as reported by the switcher
            This is a :class:`pydispatch.properties.ListProperty` and can be
            observed using the :meth:`~pydispatch.Dispatcher.bind` method.
        crosspoint_control: This is similar to :attr:`~VidhubBackendBase.crosspoints`
            but if modified from outside code, the crosspoint changes will be
            set on the device (no method calls required).
            :class:`pydispatch.properties.ListProperty`
        output_label_control: This is similar to :attr:`~VidhubBackendBase.output_labels`
            but if modified from outside code, the label changes will be written
            to the device (no method calls required).
            :class:`pydispatch.properties.ListProperty`
        input_label_control: This is similar to :attr:`~VidhubBackendBase.input_labels`
            but if modified from outside code, the label changes will be written
            to the device (no method calls required).
            :class:`pydispatch.properties.ListProperty`
        presets: The currently available (stored) ``list`` of :class:`Preset`
            instances
            :class:`pydispatch.properties.ListProperty`
    """
    crosspoints: List[int] = ListProperty()
    output_labels: List[str] = ListProperty()
    input_labels: List[str] = ListProperty()
    crosspoint_control: List[int] = ListProperty()
    output_label_control: List[str] = ListProperty()
    input_label_control: List[str] = ListProperty()
    presets: List['Preset'] = ListProperty()
    num_outputs: int = Property(0)
    num_inputs: int = Property(0)
    device_type: ClassVar[str] = 'vidhub'
    feedback_prop_map = {
        'crosspoints':'crosspoint_control',
        'input_labels':'input_label_control',
        'output_labels':'output_label_control',
    }
    _events_ = ['on_preset_added', 'on_preset_stored', 'on_preset_active']
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            num_outputs=self.on_num_outputs,
            num_inputs=self.on_num_inputs,
            output_labels=self.on_prop_feedback,
            input_labels=self.on_prop_feedback,
            crosspoints=self.on_prop_feedback,
            output_label_control=self.on_prop_control,
            input_label_control=self.on_prop_control,
            crosspoint_control=self.on_prop_control,
        )
        presets = kwargs.get('presets', [])
        for pst_data in presets:
            pst_data['backend'] = self
            preset = Preset(**pst_data)
            self.presets.append(preset)
            preset.bind(
                on_preset_stored=self.on_preset_stored,
                active=self.on_preset_active,
            )
    async def set_crosspoint(self, out_idx, in_idx):
        """Set a single crosspoint on the switcher

        Arguments:
            out_idx (int): The output to be set (zero-based)
            in_idx (int): The input to switch the output (out_idx) to (zero-based)

        """
        raise NotImplementedError()
    async def set_crosspoints(self, *args):
        """Set multiple crosspoints in one method call

        This is useful for setting many routing changes as it reduces the number
        of commands sent to the switcher.

        Arguments:
            *args: Any number of output/input pairs to set. These should be given
                as ``tuples`` of ``(out_idx, in_idx)`` as defined in
                :meth:`~BackendBase.set_crosspoint`. They can be discontinuous
                and unordered.

        """
        raise NotImplementedError()
    async def set_output_label(self, out_idx, label):
        """Set the label (name) of an output

        Arguments:
            out_idx (int): The output to be set (zero-based)
            label (str): The label for the output
        """
        raise NotImplementedError()
    async def set_output_labels(self, *args):
        """Set multiple output labels in one method call

        This is useful for setting many labels as it reduces the number
        of commands sent to the switcher.

        Arguments:
            *args: Any number of output/label pairs to set. These should be given
                as ``tuples`` of ``(out_idx, label)`` as defined in
                :meth:`~BackendBase.set_output_label`. They can be discontinuous
                and unordered.

        """
        raise NotImplementedError()
    async def set_input_label(self, in_idx, label):
        """Set the label (name) of an input

        Arguments:
            in_idx (int): The input to be set (zero-based)
            label (str): The label for the input
        """
        raise NotImplementedError()
    async def set_input_labels(self, *args):
        """Set multiple input labels in one method call

        This is useful for setting many labels as it reduces the number
        of commands sent to the switcher.

        Arguments:
            *args: Any number of input/label pairs to set. These should be given
                as ``tuples`` of ``(in_idx, label)`` as defined in
                :meth:`~BackendBase.set_input_label`. They can be discontinuous
                and unordered.

        """
        raise NotImplementedError()
    async def add_preset(self, name=None):
        """Adds a new :class:`Preset` instance

        This method is used internally and should not normally be called outside
        of this module. Instead, see :meth:`~BackendBase.store_preset`
        """
        index = len(self.presets)
        preset = Preset(backend=self, name=name, index=index)
        self.presets.append(preset)
        preset.bind(
            on_preset_stored=self.on_preset_stored,
            active=self.on_preset_active,
        )
        self.emit('on_preset_added', backend=self, preset=preset)
        return preset
    async def store_preset(self, outputs_to_store=None, name=None, index=None, clear_current=True):
        """Store the current switcher state to a :class:`Preset`

        Arguments:
            outputs_to_store (optional): An iterable of the output numbers
                (zero-based) that should be saved in the preset. If given, only
                these outputs will be recorded and when recalled, any output
                not in this argument will be unchanged. If not given or ``None``,
                all outputs will be recorded.
            name (optional): The name to be given to the preset. If not provided
                or ``None`` the preset will be given a name based off of its index.
            index (optional): The index for the preset. If given and the preset
                exists in the :attr:`~BackendBase.presets` list, that preset
                will be updated. If there is no preset found with the index,
                a new one will be created. If not given or ``None``, the next
                available index will be used and a new preset will be created.
            clear_current (bool): If ``True``, any previously existing data will
                be removed from the preset (if it exists). If ``False``, the
                data (if existing) will be merged with the current switcher state.
                Default is ``True``

        Returns:
            The :class:`Preset` instance that was created or updated

        This method is a ``coroutine``

        """
        if index is None:
            preset = await self.add_preset()
        else:
            while True:
                try:
                    preset = self.presets[index]
                except IndexError:
                    preset = None
                if preset is not None:
                    break
                preset = await self.add_preset()
        if name is not None:
            preset.name = name
        await preset.store(outputs_to_store, clear_current)
        return preset
    def on_preset_stored(self, *args, **kwargs):
        kwargs['backend'] = self
        self.emit('on_preset_stored', *args, **kwargs)
    def on_preset_active(self, instance, value, **kwargs):
        self.emit('on_preset_active', backend=self, preset=instance, value=value)
    def on_num_outputs(self, instance, value, **kwargs):
        if value == len(self.output_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.output_labels = [''] * value
    def on_num_inputs(self, instance, value, **kwargs):
        if value == len(self.input_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.input_labels = [''] * value
    def on_prop_feedback(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        if prop.name not in self.feedback_prop_map:
            return
        elock = self.emission_lock(prop.name)
        control_prop = self.feedback_prop_map[prop.name]
        setattr(self, control_prop, value[:])
    def on_prop_control(self, instance, value, **kwargs):
        if not self.connection_state.is_connected:
            return
        if not self.prelude_parsed:
            return
        prop = kwargs.get('property')
        keys = kwargs.get('keys')
        if keys is None:
            keys = range(len(value))
        feedback_prop = '{}s'.format(prop.name.split('_control')[0])
        elock = self.emission_lock(feedback_prop)
        if elock.held:
            return
        ## TODO:    This is an internal implementation in python-dispatch and
        ##          is subject to future changes.
        aio_lock = elock.aio_locks.get(id(self.event_loop))
        if aio_lock is not None and aio_lock.locked():
            return
        if value == getattr(self, feedback_prop):
            return
        coro_name = '_'.join(['set', feedback_prop])
        coro = getattr(self, coro_name)
        args = [(key, value[key]) for key in keys]
        tx_fut = asyncio.run_coroutine_threadsafe(coro(*args), loop=self.event_loop)

class SmartViewBackendBase(BackendBase):
    """Base class for SmartView devices

    Attributes:
        num_monitors: Number of physical monitors as reported by the device
        inverted: ``True`` if the device has been mounted in an inverted
            configuration (to optimize viewing angle).
        monitors: A ``list`` containing instances of :class:`SmartViewMonitor`
            or :class:`SmartScopeMonitor`, depending on device type.

    :Events:
        .. function:: on_monitor_property_change(self: SmartViewBackendBase, name: str, value: Any, monitor: SmartViewMonitor = monitor)

            Dispatched when any :class:`~pydispatch.properties.Property`
            value changes. The event signature for callbacks is
            ``(smartview_device, property_name, value, **kwargs)`` containing
            a keyword argument "monitor" containing the :class:`SmartViewMonitor`
            instance.

    """
    num_monitors: Optional[int] = Property()
    inverted: bool = Property(False)
    monitors: List['SmartViewMonitor'] = ListProperty()
    monitor_cls: ClassVar[type] = None
    device_type: ClassVar[str] = 'smartview'
    _events_ = ['on_monitor_property_change']
    def __init__(self, **kwargs):
        self.bind(monitors=self._on_monitors)
        super().__init__(**kwargs)
    async def set_monitor_property(self, monitor, name, value):
        """Set a property value for the given :class:`SmartViewMonitor` instance

        Arguments:
            monitor: The :class:`SmartViewMonitor` instance to set
            name (str): Property name
            value: The new value to set

        This method is a coroutine.

        """
        raise NotImplementedError()
    def get_monitor_cls(self):
        cls = self.monitor_cls
        if cls is None:
            cls = SmartViewMonitor
        return cls
    async def add_monitor(self, **kwargs):
        cls = self.get_monitor_cls()
        kwargs.setdefault('parent', self)
        kwargs.setdefault('index', len(self.monitors))
        monitor = cls(**kwargs)
        monitor.bind(on_property_change=self.on_monitor_prop)
        self.monitors.append(monitor)
        return monitor
    def on_monitor_prop(self, instance, name, value, **kwargs):
        kwargs['monitor'] = instance
        self.emit('on_monitor_property_change', self, name, value, **kwargs)
    def _on_monitors(self, *args, **kwargs):
        self.num_monitors = len(self.monitors)

class SmartScopeBackendBase(SmartViewBackendBase):
    device_type: ClassVar[str] = 'smartscope'
    def get_monitor_cls(self):
        cls = self.monitor_cls
        if cls is None:
            cls = SmartScopeMonitor
        return cls

MONITOR_PROPERTY_MAP = {k:k.title() for k in [
    'brightness', 'contrast', 'saturation', 'identify', 'border']}
MONITOR_PROPERTY_MAP.update({
    'widescreen_sd':'WidescreenSD',
    'audio_channel':'AudioChannel',
    'scope_mode':'ScopeMode',
})

class SmartViewMonitor(Dispatcher):
    """A single instance of a monitor within a SmartView device

    Attributes:
        index: Index of the monitor (zero-based)
        name: The name of the monitor (can be user-defined)
        brightness: The brightness value of the monitor (0-255)
        contrast: The contrast value of the monitor (0-255)
        saturation: The saturation value of the monitor (0-255)
        widescreen_sd: Aspect ratio setting for SD format. Choices can be:
            ``True`` (stretching enabled), ``False`` (pillar-box), or
            ``None`` (auto-detect).
        identify: If set to ``True``, the monitor's border will be white
            for a brief duration to physically locate the device.
        border: Sets the border of the monitor to the given color. Choices
            are: 'red', 'green', 'blue', 'white', or ``None``.
        audio_channel: The audio channel pair (Embedded in the SDI input)
            used when :attr:`scope_mode` is set to audio monitoring.
            Values are from 0 to 7 (0 == Channels 1&2, etc).

    """
    index: int = Property()
    name: str = Property()
    brightness: int = Property()
    contrast: int = Property()
    saturation: int = Property()
    widescreen_sd: Optional[bool] = Property()
    identify: bool = Property(False)
    border: Optional[str] = Property()
    audio_channel: int = Property()
    class PropertyChoices():
        widescreen_sd = {
            True:'ON',
            False:'OFF',
            None:'auto',
        }
        border = {
            'red':'red',
            'green':'green',
            'blue':'blue',
            'white':'white',
            None:'NONE',
        }
        identify = {
            True:'true',
            False:'false',
        }
        _bind_properties = [
            'brightness', 'contrast', 'saturation',
            'widescreen_sd', 'identify', 'border', 'audio_channel',
        ]
    _events_ = ['on_property_change']
    def __init__(self, **kwargs):
        self._property_locks = {}
        self.parent = kwargs.get('parent')
        self.event_loop = self.parent.event_loop
        self.index = kwargs.get('index')
        self.name = kwargs.get('name')
        props = self.PropertyChoices._bind_properties
        for prop in props:
            value = kwargs.get(prop)
            value = self.get_property_for_choice(prop, value)
            setattr(self, prop, value)
        self.bind(**{prop:self.on_prop_control for prop in props})
    def _get_property_lock(self, name):
        lock = self._property_locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self._property_locks[name] = lock
        return lock
    async def set_property_from_backend(self, name, value):
        value = self.get_property_for_choice(name, value)
        lock = self._get_property_lock(name)
        async with lock:
            setattr(self, name, value)
        self.emit('on_property_change', self, name, value)
    async def set_property(self, name, value):
        await self.parent.set_monitor_property(self, name, value)
    async def flash(self):
        await self.set_property('identify', True)
    def get_property_choices(self, name):
        return getattr(self.PropertyChoices, name, None)
    def get_choice_for_property(self, name, value):
        choices = self.get_property_choices(name)
        if choices is not None:
            if value in choices:
                value = choices[value]
        return value
    def get_property_for_choice(self, name, value):
        choices = self.get_property_choices(name)
        if choices is not None:
            if value in choices.values():
                for k, v in choices.items():
                    if v == value:
                        value = k
                        break
        if isinstance(value, str) and value.lower() in ('none', 'true', 'false'):
            if value.lower() == 'none':
                value = None
            else:
                value = value.lower() == 'true'
        return value
    def on_prop_control(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        lock = self._get_property_lock(prop.name)
        if lock.locked():
            return
        value = self.get_choice_for_property(prop.name, value)
        fut = self.set_property(prop.name, value)
        asyncio.run_coroutine_threadsafe(fut, loop=self.event_loop)


class SmartScopeMonitor(SmartViewMonitor):
    """A single instance of a monitor within a SmartScope device

    Attributes:
        scope_mode: The type of scope to display.  Choices are:
            'audio_dbfs', 'audio_dbvu', 'histogram', 'parade_rgb', 'parade_yuv',
            'video', 'vector_100', 'vector_75', 'waveform'.

    """
    scope_mode: str = Property()
    class PropertyChoices(SmartViewMonitor.PropertyChoices):
        scope_mode = {
            'audio_dbfs':'AudioDbfs',
            'audio_dbvu':'AudioDbvu',
            'histogram':'Histogram',
            'parade_rgb':'ParadeRGB',
            'parade_yuv':'ParadeYUV',
            'video':'Picture',
            'vector_100':'Vector100',
            'vector_75':'Vector75',
            'waveform':'WaveformLuma',
        }
        _bind_properties = SmartViewMonitor.PropertyChoices._bind_properties + [
            'scope_mode',
        ]


class Preset(Dispatcher):
    """Stores and recalls routing information

    Attributes:
        name: The name of the preset.
            This is a :class:`pydispatch.Property`
        index: The index of the preset as it is stored in the
            :attr:`~BackendBase.presets` container.
        crosspoints: The crosspoints that this preset has stored.
            This is a :class:`~pydispatch.properties.DictProperty`
        active: A flag indicating whether all of the crosspoints stored
            in this preset are currently active on the switcher.
            This is a :class:`pydispatch.Property`

    :Events:
        .. function:: on_preset_stored(preset: Preset = self)

            Dispatched after the preset stores its state.

    """
    name: str = Property()
    index: int = Property()
    crosspoints: Dict[int, int] = DictProperty()
    active: bool = Property(False)
    _events_ = ['on_preset_stored']
    def __init__(self, **kwargs):
        self.backend = kwargs.get('backend')
        self.index = kwargs.get('index')
        name = kwargs.get('name')
        if name is None:
            name = 'Preset {}'.format(self.index + 1)
        self.name = name
        self.crosspoints = kwargs.get('crosspoints', {})
        if self.backend.connection_state.is_connected and self.backend.prelude_parsed:
            self.check_active()
        else:
            self.backend.bind(prelude_parsed=self.on_backend_ready)
        self.backend.bind(crosspoints=self.on_backend_crosspoints)
        self.bind(crosspoints=self.on_preset_crosspoints)
    async def store(self, outputs_to_store=None, clear_current=True):
        if outputs_to_store is None:
            outputs_to_store = range(self.backend.num_outputs)
        if clear_current:
            self.crosspoints = {}
        async with self.emission_lock('crosspoints'):
            for out_idx in outputs_to_store:
                self.crosspoints[out_idx] = self.backend.crosspoints[out_idx]
            self.active = True
        self.emit('on_preset_stored', preset=self)
    async def recall(self):
        if not len(self.crosspoints):
            return
        args = [(i, v) for i, v in self.crosspoints.items()]
        await self.backend.set_crosspoints(*args)
    def check_active(self):
        if not len(self.crosspoints):
            self.active = False
            return
        for out_idx, in_idx in self.crosspoints.items():
            in_idx = self.crosspoints[out_idx]
            if self.backend.crosspoints[out_idx] != in_idx:
                self.active = False
                return
        self.active = True
    def on_backend_ready(self, instance, value, **kwargs):
        if not value:
            return
        self.backend.unbind(self.on_backend_ready)
        self.check_active()
    def on_backend_crosspoints(self, instance, value, **kwargs):
        if not self.backend.prelude_parsed:
            return
        self.check_active()
    def on_preset_crosspoints(self, instance, value, **kwargs):
        if not len(self.crosspoints) or not self.backend.prelude_parsed:
            return
        self.check_active()
