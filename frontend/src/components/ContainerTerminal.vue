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
          :items="['/bin/sh', '/bin/bash', '/bin/ash', '/bin/zsh']"
          dense
          hide-details
          outlined
          class="mr-4"
          style="max-width: 150px;"
          label="Shell"
          @change="reconnect"
        ></v-select>

        <v-btn icon @click="reconnect">
          <v-icon>mdi-refresh</v-icon>
        </v-btn>

        <v-btn icon @click="close">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-toolbar>

      <v-card-text class="flex-grow-1 pa-0 black">
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
    selectedShell: '/bin/bash',
    resizeObserver: null
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
      this.fitAddon.fit();

      this.connect();

      window.addEventListener('resize', this.handleResize);
      this.terminal.onResize(this.sendResize);

      this.resizeObserver = new ResizeObserver(() => {
          this.fit();
      });
      this.resizeObserver.observe(this.$refs.terminal);
    },
    connect() {
      if (this.websocket) {
        this.websocket.close();
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : '';

      const wsUrl = `${protocol}//${host}${port}/api/containers/${this.containerId}/exec?shell=${this.selectedShell}`;

      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
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
        this.terminal.write(`\r\n\x1b[31mDisconnected (Code: ${event.code})\x1b[0m\r\n`);
      };

      this.websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.terminal.write('\r\n\x1b[31mConnection Error\x1b[0m\r\n');
      };

      this.terminal.onData(data => {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
          this.websocket.send(data);
        }
      });
    },
    fit() {
        if (this.fitAddon) {
            this.fitAddon.fit();
            this.sendResize({ cols: this.terminal.cols, rows: this.terminal.rows });
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
    }
  },
  beforeDestroy() {
    this.dispose();
  }
};
</script>

<style scoped>
</style>
