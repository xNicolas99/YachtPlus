# Apache Reverse Proxy Configuration for YachtPlus

If you are running YachtPlus behind an Apache Reverse Proxy, you must enable `mod_proxy_wstunnel` and configure the VirtualHost to correctly handle WebSocket upgrades and Server-Sent Events (SSE).

## Prerequisites

Enable necessary Apache modules:

```bash
a2enmod proxy
a2enmod proxy_http
a2enmod proxy_wstunnel
a2enmod rewrite
systemctl restart apache2
```

## VirtualHost Configuration

Add the following configuration to your Apache VirtualHost definition. Replace `yachtplus.example.com` and `http://localhost:8000` with your actual domain and the YachtPlus internal address/port.

```apache
<VirtualHost *:80>
    ServerName yachtplus.example.com

    ProxyPreserveHost On
    ProxyRequests Off

    # Allow encoded slashes
    AllowEncodedSlashes NoDecode

    # WebSocket Support (Critical for Terminal)
    # Redirect Upgrade requests to the websocket backend
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteRule /(.*)           ws://localhost:8000/$1 [P,L]

    # SSE Support (Critical for Stats/Logs)
    # Disable buffering to allow real-time events
    <Location /api>
        SetEnv proxy-nokeepalive 1
        SetEnv proxy-sendchunked 1
    </Location>

    # General Proxy Pass
    ProxyPass / http://localhost:8000/
    ProxyPassReverse / http://localhost:8000/

    # Optional: Increase timeout for long docker operations
    ProxyTimeout 300
</VirtualHost>
```

### Explanation of Fixes

1.  **RewriteRule for WebSockets**: explicitly checks for `Upgrade: websocket` header and proxies via `ws://`.
2.  **SSE Buffering**: SSE (Server-Sent Events) requires a persistent connection without buffering. If Apache buffers the response, the UI will show 0% stats or loading logs forever. Configuring `proxy-nokeepalive` and `proxy-sendchunked` helps ensure data flows immediately.
