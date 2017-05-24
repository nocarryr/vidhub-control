import ipaddress
try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError: # pragma: no cover
    netifaces = None
    NETIFACES_AVAILABLE = False

def find_ip_addresses(iface_name=None, exclude_loopback=True):
    if not NETIFACES_AVAILABLE:
        yield 'lo', ipaddress.IPv4Interface('127.0.0.1/8')
        iface_names = []
    elif iface_name is not None:
        iface_names = [iface_name]
    else:
        iface_names = netifaces.interfaces()
    for iface_name in iface_names:
        try:
            addrs = netifaces.ifaddresses(iface_name)[netifaces.AF_INET]
        except KeyError:
            continue
        for addr in addrs:
            iface = ipaddress.IPv4Interface('/'.join([addr['addr'], addr['netmask']]))
            if iface.is_loopback and exclude_loopback:
                continue
            if iface.is_reserved:
                continue
            yield iface_name, iface
