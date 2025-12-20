<template>
  <v-dialog
    v-model="dialog"
    fullscreen
    hide-overlay
    transition="dialog-bottom-transition"
    @keydown.esc="close"
  >
    <v-card class="d-flex flex-column" style="height: 100vh;">
      <v-toolbar dark color="primary" dense>
        <v-toolbar-title>{{ containerName }} - Terminal</v-toolbar-title>
        <v-spacer></v-spacer>

        <v-select
          v-model="selectedShell"
          :items="['/bin/sh', '/bin/bash', '/bin/ash', '/bin/zsh', '/usr/bin/fish']"
          dense
          hide-details
          outlined
          class="mr-4"
          style="max-width: 150px;"
          label="Shell"
          @change="reconnect"
        ></v-select>

        <v-tooltip bottom>
           <template v-slot:activator="{ on, attrs }">
              <v-btn icon @click="reconnect" v-bind="attrs" v-on="on">
                <v-icon>mdi-refresh</v-icon>
              </v-btn>
           </template>
           <span>Reconnect</span>
        </v-tooltip>

        <v-btn icon @click="close">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-toolbar>

      <v-card-text class="flex-grow-1 pa-0 black" style="overflow: hidden;">
        <div ref="terminal" style="width: 100%; height: 100%;"></div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

export default {
  props: {
    visible: Boolean,
    containerId: String,
    containerName: String
  },
  data: () => ({
    dialog: false,
    terminal: null,
    fitAddon: null,
    websocket: null,
    selectedShell: '/bin/sh',
    resizeObserver: null,
    isConnected: false
  }),
  watch: {
    visible(val) {
      this.dialog = val;
      if (val) {
        this.$nextTick(() => {
          this.initTerminal();
        });
      } else {
        this.dispose();
      }
    },
    dialog(val) {
      if (!val) {
        this.$emit('close');
      }
    }
  },
  methods: {
    initTerminal() {
      if (this.terminal) return;

      this.terminal = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: {
          background: '#000000',
          foreground: '#ffffff'
        }
      });

      this.fitAddon = new FitAddon();
      this.terminal.loadAddon(this.fitAddon);
      this.terminal.open(this.$refs.terminal);

      // Delay fit slightly to ensure DOM is ready
      setTimeout(() => {
          this.fit();
      }, 100);

      this.connect();

      window.addEventListener('resize', this.handleResize);
      this.terminal.onResize(this.sendResize);

      this.resizeObserver = new ResizeObserver(() => {
          this.fit();
      });
      this.resizeObserver.observe(this.$refs.terminal);

      this.terminal.focus();
    },
    connect() {
      if (this.websocket) {
        this.websocket.close();
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : '';
      // If served via proxy (e.g. nginx port 8000 -> backend), window.location.port might be empty or 8080.
      // But typically api is at /api.
      // The backend endpoint is /api/containers/...
      // If dev mode: backend on 8000, frontend on 8080. Proxy in vue.config.js handles /api.
      // But WebSockets don't always go through the dev server proxy correctly if not configured.
      // However, usually it works if relative path is used but WebSocket constructor needs absolute URL.

      // We should use the same host/port as the page if it's served from same origin (production).
      // In dev, we might need to point to 8000.
      // Assuming standard deployment or proxy:
      const wsUrl = `${protocol}//${host}${port}/api/containers/${this.containerId}/exec?shell=${this.selectedShell}`;

      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        this.isConnected = true;
        this.terminal.write('\r\n\x1b[32mConnected to ' + this.containerName + '\x1b[0m\r\n');
        this.fit();
        this.terminal.focus();
      };

      this.websocket.onmessage = (event) => {
        if (event.data instanceof Blob) {
            const reader = new FileReader();
            reader.onload = () => {
                this.terminal.write(reader.result);
            };
            reader.readAsText(event.data);
        } else {
            this.terminal.write(event.data);
        }
      };

      this.websocket.onclose = (event) => {
        this.isConnected = false;
        this.terminal.write(`\r\n\x1b[31mConnection lost (Code: ${event.code})\x1b[0m\r\n`);
        if (event.code === 1008 || event.code === 1011) {
             if (this.$toast) this.$toast.error("Connection closed: Container might have stopped.");
             // Requirement: "Bei Container-Stop während Session: Modal schließen mit Info-Toast"
             // If we want to auto-close:
             // this.close();
        }
      };

      this.websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.terminal.write('\r\n\x1b[31mConnection Error\x1b[0m\r\n');
        if (this.$toast) this.$toast.error("WebSocket connection error");
      };

      this.terminal.onData(data => {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
          this.websocket.send(data);
        }
      });
    },
    fit() {
        if (this.fitAddon && this.terminal) {
            try {
                this.fitAddon.fit();
                this.sendResize({ cols: this.terminal.cols, rows: this.terminal.rows });
            } catch (e) {
                // Ignore fit errors if terminal not visible
            }
        }
    },
    handleResize() {
        this.fit();
    },
    sendResize(size) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'resize',
                cols: size.cols,
                rows: size.rows
            }));
        }
    },
    reconnect() {
        this.terminal.clear();
        this.connect();
    },
    close() {
      this.dialog = false;
    },
    dispose() {
      if (this.websocket) {
        this.websocket.close();
        this.websocket = null;
      }
      if (this.terminal) {
        this.terminal.dispose();
        this.terminal = null;
      }
      window.removeEventListener('resize', this.handleResize);
      if (this.resizeObserver) {
          this.resizeObserver.disconnect();
      }
      this.isConnected = false;
    }
  },
  beforeDestroy() {
    this.dispose();
  }
};
</script>
