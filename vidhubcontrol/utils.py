import ipaddress
import netifaces

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