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
    isConnected: false,
    copyTimeout: null
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

      // Auto-Copy on Selection with Debounce
      this.terminal.onSelectionChange(() => {
        if (this.copyTimeout) clearTimeout(this.copyTimeout);
        this.copyTimeout = setTimeout(() => {
            const selection = this.terminal.getSelection();
            if (selection) {
              navigator.clipboard.writeText(selection).catch(err => {
                 console.error('Failed to copy text: ', err);
              });
            }
        }, 200);
      });

      // Right-Click Paste
      this.$refs.terminal.addEventListener('contextmenu', this.handleContextPaste);

      this.terminal.focus();
    },
    handleContextPaste(e) {
      e.preventDefault();
      navigator.clipboard.readText()
        .then(text => {
           if (text && this.terminal) {
             this.terminal.paste(text);
           }
        })
        .catch(err => {
           console.error('Failed to read clipboard: ', err);
           if (this.$toast) this.$toast.error('Failed to paste from clipboard. Check permissions.');
        });
    },
    connect() {
      if (this.websocket) {
        this.websocket.close();
      }

      // Get auth token from store or localStorage
      const token = localStorage.getItem('token') || sessionStorage.getItem('token') || this.$store.state.auth.token || localStorage.getItem('authToken') || localStorage.getItem('access_token_cookie');

      if (!token) {
        if (this.$toast) this.$toast.error('Authentication required. Please log in again.');
        return;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : '';

      const wsUrl = `${protocol}//${host}${port}/api/containers/${this.containerId}/exec?token=${encodeURIComponent(token)}&shell=${this.selectedShell}`;

      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        this.isConnected = true;
        this.terminal.write('\r\n\x1b[32mConnected to ' + this.containerName + '\x1b[0m\r\n');
        this.fit();
        this.terminal.focus();
      };

      this.websocket.onmessage = (event) => {
        try {
            // Check if it's a JSON error message
            const data = JSON.parse(event.data);
            if (data.error) {
                if (this.$toast) this.$toast.error(`Shell error: ${data.error}`);
                this.websocket.close();
                return;
            }
        } catch (e) {
            // Not JSON, assume terminal output
        }

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

        if (event.code === 1008) {
             if (this.$toast) this.$toast.error('Unauthorized: Session expired. Please log in again.');
        } else if (event.code === 1003) {
             if (this.$toast) this.$toast.warning(`Connection closed: ${event.reason || 'Container not available'}`);
        } else if (event.code === 1011) {
             if (this.$toast) this.$toast.error("Internal server error.");
        } else if (event.code !== 1000) {
             // Generic close
        }
      };

      this.websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.terminal.write('\r\n\x1b[31mConnection Error\x1b[0m\r\n');
        if (this.$toast) this.$toast.error("WebSocket connection error. Check if container is running.");
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
        // Remove context menu listener
        if (this.$refs.terminal) {
            this.$refs.terminal.removeEventListener('contextmenu', this.handleContextPaste);
        }
        this.terminal.dispose();
        this.terminal = null;
      }
      if (this.copyTimeout) {
        clearTimeout(this.copyTimeout);
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
