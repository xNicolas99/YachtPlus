export function containerPortLink(port, currentLocation) {
  let host = !port.hip || ['0.0.0.0', '::'].includes(port.hip) ? currentLocation.hostname : port.hip;
  if (host.includes(':') && !host.startsWith('[')) host = `[${host}]`;
  const protocol = ['443', '8443'].includes(String(port.hport)) ? 'https:' : currentLocation.protocol;
  return `${protocol}//${host}:${port.hport}`;
}
