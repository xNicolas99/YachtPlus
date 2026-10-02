"""Generate nginx trusted proxy directives from validated IP networks only."""

import ipaddress
import os
from pathlib import Path


def proxy_configuration(value: str) -> tuple[str, str]:
    networks = []
    for item in value.split(','):
        if item.strip():
            networks.append(str(ipaddress.ip_network(item.strip(), strict=False)))
    real_ip = ''.join(f'set_real_ip_from {network};\n' for network in networks)
    if networks:
        real_ip += 'real_ip_header X-Forwarded-For;\nreal_ip_recursive on;\n'
    geo = ''.join(f'{network} 1;\n' for network in networks)
    return real_ip, geo


def main() -> None:
    try:
        real_ip, geo = proxy_configuration(os.environ.get('YACHT_HTTP_TRUSTED_PROXIES', ''))
    except ValueError as exc:
        raise SystemExit(f'Invalid YACHT_HTTP_TRUSTED_PROXIES: {exc}') from exc
    directory = Path('/var/run/nginx')
    for name, content in [('trusted-proxies.conf', real_ip), ('trusted-proxy-geo.conf', geo)]:
        temporary = directory / (name + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(directory / name)


if __name__ == '__main__':
    main()
