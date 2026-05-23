# Apache Reverse Proxy Configuration for YachtPlus

If you are running YachtPlus behind an Apache Reverse Proxy, you must enable
`mod_proxy_wstunnel` and configure the VirtualHost to correctly handle
WebSocket upgrades and Server-Sent Events (SSE).

> **Do not expose YachtPlus over plain HTTP.** The session cookie is
> `HttpOnly` but not `Secure` unless the connection is encrypted, and the
> JWT it carries lets anyone on the wire impersonate you. Use HTTPS at the
> public listener; the `http://localhost:8000` proxy target is loopback
> traffic and is fine to keep plain. The `ws://localhost:8000` upstream URL
> in the RewriteRule below is also loopback — the **public** WebSocket
> reaches the browser as `wss://` automatically because the public
> listener is TLS.

## Prerequisites

Enable necessary Apache modules:

```bash
a2enmod proxy
a2enmod proxy_http
a2enmod proxy_wstunnel
a2enmod rewrite
a2enmod ssl
a2enmod headers
systemctl restart apache2
```

## VirtualHost Configuration

Add the following to your Apache config. Replace `yachtplus.example.com`,
the certificate paths, and `http://localhost:8000` with your real values.

```apache
# Redirect every HTTP request to HTTPS so users can't accidentally send
# the auth cookie over an unencrypted connection.
<VirtualHost *:80>
    ServerName yachtplus.example.com
    Redirect permanent / https://yachtplus.example.com/
</VirtualHost>

<VirtualHost *:443>
    ServerName yachtplus.example.com

    SSLEngine on
    SSLCertificateFile      /etc/letsencrypt/live/yachtplus.example.com/fullchain.pem
    SSLCertificateKeyFile   /etc/letsencrypt/live/yachtplus.example.com/privkey.pem
    SSLProtocol             all -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite          HIGH:!aNULL:!MD5
    SSLHonorCipherOrder     on

    # HSTS — tells the browser to refuse plain HTTP for one year.
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"

    ProxyPreserveHost On
    ProxyRequests Off

    # Allow encoded slashes
    AllowEncodedSlashes NoDecode

    # WebSocket Support (Critical for Terminal)
    # Redirect Upgrade requests to the websocket backend over loopback.
    # The PUBLIC connection from the browser to Apache is wss:// because
    # this VirtualHost listens on 443 with TLS.
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteRule /(.*)           ws://localhost:8000/$1 [P,L]

    # SSE Support (Critical for Stats/Logs)
    # Disable buffering to allow real-time events
    <Location /api>
        SetEnv proxy-nokeepalive 1
        SetEnv proxy-sendchunked 1
    </Location>

    # General Proxy Pass — loopback traffic, fine to be plain HTTP.
    ProxyPass / http://localhost:8000/
    ProxyPassReverse / http://localhost:8000/

    # Optional: Increase timeout for long docker operations
    ProxyTimeout 300
</VirtualHost>
```

### Explanation

1. **TLS at the public listener.** The session cookie does NOT have the
   `Secure` flag when the connection is plain HTTP, which means the
   browser will happily send it over the wire in clear text. Anyone with
   network visibility (other LAN users, hotel Wi-Fi, hostile DNS upstream)
   can capture and replay it.
2. **HSTS.** Once a user has loaded the site over HTTPS once, HSTS pins
   the requirement for one year. This blocks accidental downgrade attacks
   even when a user types `http://yachtplus.example.com`.
3. **RewriteRule for WebSockets.** Apache matches the `Upgrade: websocket`
   header and proxies the connection via `ws://` to the loopback backend.
4. **SSE Buffering.** SSE requires a persistent connection without
   buffering. Without `proxy-nokeepalive` + `proxy-sendchunked` the UI
   shows 0% stats or empty logs because Apache buffers the chunked stream.
