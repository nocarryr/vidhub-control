import asyncio
import ipaddress

from kivy.properties import (
    ObjectProperty,
    NumericProperty,
    StringProperty,
    BooleanProperty,
    OptionProperty,
    ListProperty,
    DictProperty,
)
from kivy.uix.popup import Popup

from vidhubcontrol.config import BACKENDS

class NewDevicePopup(Popup):
    app = ObjectProperty(None)
    name = StringProperty('')
    ip_address = StringProperty('')
    port = StringProperty('9990')
    name_widget = ObjectProperty(None)
    ip_widget = ObjectProperty(None)
    port_widget = ObjectProperty(None)
    device_type = StringProperty()
    def validate(self):
        valid = True
        self.ip_widget.validation_error = False
        self.port_widget.validation_error = False
        if not len(self.ip_address):
            self.ip_widget.validation_message = 'Required Field'
            self.ip_widget.validation_error = True
            valid = False
        else:
            try:
                addr = ipaddress.ip_address(self.ip_address)
            except ValueError:
                self.ip_widget.validation_message = 'Invalid Address'
                self.ip_widget.validation_error = True
                valid = False
        if not len(self.port):
            self.port_widget.validation_message = 'Required Field'
            self.port_widget.validation_error = True
            valid = False
        elif not self.port.isdigit():
            self.port_widget.validation_message = 'Integer Required'
            self.port_widget.validation_error = True
            valid = False
        return valid
    def on_submit(self, *args, **kwargs):
        if not self.validate():
            return
        self.add_device()
        self.dismiss()
    def add_device(self):
        for name in BACKENDS[self.device_type]:
            if 'Dummy' not in name:
                backend_name = name
                break
        config = self.app.vidhub_config
        kw = {'hostaddr':self.ip_address, 'hostport':int(self.port)}
        if len(self.name):
            kw['device_name'] = self.name
        self.app.run_async_coro(config.build_backend(self.device_type, backend_name, **kw))
