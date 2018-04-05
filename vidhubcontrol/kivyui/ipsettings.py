import asyncio
import ipaddress

from kivy.properties import (
    ObjectProperty,
    StringProperty,
    BooleanProperty,
)
from kivy.uix.popup import Popup

class IPSettingsPopup(Popup):
    app = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    ip_widget = ObjectProperty(None)
    netmask_widget = ObjectProperty(None)
    gateway_widget = ObjectProperty(None)
    use_dhcp = BooleanProperty(False)
    ip_address = StringProperty('')
    netmask = StringProperty('')
    gateway = StringProperty('')
    device_use_dhcp = BooleanProperty(False)
    device_ip = ObjectProperty(ipaddress.ip_interface('0.0.0.0/32'))
    device_gateway = ObjectProperty(ipaddress.ip_address('0.0.0.0'))
    def on_device(self, *args):
        device = self.device
        self.use_dhcp = device.using_dhcp
        self.ip_address = str(device.static_ip.ip)
        self.netmask = str(device.static_ip.netmask)
        self.gateway = str(device.static_gateway)
        self.device_use_dhcp = device.using_dhcp
        self.device_ip = device.current_ip
        self.device_gateway = device.current_gateway
    def validate_ip_prop(self, prop, widget):
        address = getattr(self, prop)
        if not len(address):
            widget.validation_message = 'Required Field'
            widget.validation_error = True
            return False
        try:
            addr = ipaddress.ip_address(address)
        except ValueError:
            widget.validation_message = 'Invalid Address'
            widget.validation_error = True
            return False
        return True
    def validate(self):
        self.ip_widget.validation_error = False
        self.netmask_widget.validation_error = False
        self.gateway_widget.validation_error = False
        if self.use_dhcp:
            return True
        r = set()
        r.add(self.validate_ip_prop('ip_address', self.ip_widget))
        r.add(self.validate_ip_prop('netmask', self.netmask_widget))
        r.add(self.validate_ip_prop('gateway', self.gateway_widget))
        if False in r:
            return False
        addr = ipaddress.ip_interface('/'.join([self.ip_address, self.netmask]))
        gateway = ipaddress.ip_address(self.gateway)
        if gateway not in addr.network:
            self.gateway_widget.validation_message = 'Invalid gateway for network'
            self.gateway_widget.validation_error = True
            return False
        return True
    def on_submit(self, *args, **kwargs):
        if not self.validate():
            return
        self.submit_changes()
        self.dismiss()
    def submit_changes(self):
        if self.use_dhcp:
            self.app.run_async_coro(self.device.set_dhcp())
        else:
            addr = ipaddress.ip_interface('/'.join([self.ip_address, self.netmask]))
            gateway = ipaddress.ip_address(self.gateway)
            self.app.run_async_coro(self.device.set_device_static_ip(addr, gateway))
