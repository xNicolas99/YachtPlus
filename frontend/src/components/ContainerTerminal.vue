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
          :items="[
            '/bin/sh',
            '/bin/bash',
            '/bin/ash',
            '/bin/zsh',
            '/usr/bin/fish'
          ]"
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
            <v-btn icon @click="reconnect" v-bind="attrs" v-on="on" aria-label="Reconnect terminal">
              <v-icon>mdi-refresh</v-icon>
            </v-btn>
          </template>
          <span>Reconnect</span>
        </v-tooltip>

        <v-tooltip bottom>
          <template v-slot:activator="{ on, attrs }">
            <v-btn icon @click="pasteFromClipboard" v-bind="attrs" v-on="on" aria-label="Paste from clipboard">
              <v-icon>mdi-content-paste</v-icon>
            </v-btn>
          </template>
          <span>Paste</span>
        </v-tooltip>

        <v-btn icon @click="close" aria-label="Close terminal">
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
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";

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
    dataDisposable: null, // To store the listener reference
    selectedShell: "/bin/sh",
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
        this.$emit("close");
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
          background: "#000000",
          foreground: "#ffffff"
        },
        convertEol: true, // Helpful for some shell outputs
        disableStdin: false // Ensure input is allowed (default)
      });

      this.fitAddon = new FitAddon();
      this.terminal.loadAddon(this.fitAddon);
      this.terminal.open(this.$refs.terminal);

      // Delay fit slightly to ensure DOM is ready
      setTimeout(() => {
        this.fit();
      }, 100);

      this.connect();

      window.addEventListener("resize", this.handleResize);
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
            this.handleCopy(selection);
          }
        }, 100);
      });

      // Right-Click Paste
      this.$refs.terminal.addEventListener(
        "contextmenu",
        this.handleContextPaste
      );

      this.terminal.focus();
    },
    async handleCopy(text) {
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        if (this.$toast) this.$toast.success("Copied to clipboard!");
      } catch (err) {
        // Fallback for HTTP
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        textarea.style.top = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
          const successful = document.execCommand("copy");
          if (successful && this.$toast)
            this.$toast.success("Copied to clipboard!");
        } catch (e) {
          console.error("Failed to copy", e);
        }
        document.body.removeChild(textarea);
      }
    },
    async pasteFromClipboard() {
      if (navigator.clipboard && navigator.clipboard.readText) {
        try {
          const text = await navigator.clipboard.readText();
          if (text && this.terminal) {
             // Paste via terminal's handler which sends data to backend
             this.terminal.paste(text);
          }
        } catch (err) {
           if (this.$toast) this.$toast.info("Please use Ctrl+V to paste.");
        }
      } else {
        // Fallback notice
        if (this.$toast) this.$toast.info("Please use Ctrl+V to paste.");
      }
    },
    async handleContextPaste(e) {
      e.preventDefault();
      await this.pasteFromClipboard();
    },
    connect() {
      // 1. Close old WebSocket connection
      if (this.websocket) {
        this.websocket.close(1000, 'Switching shell or reconnecting');
        this.websocket = null;
      }

      // 2. Remove old event listener
      if (this.dataDisposable) {
        this.dataDisposable.dispose();
        this.dataDisposable = null;
      }

      // 3. Clear terminal (optional but good practice when switching shells)
      if (this.terminal) {
        this.terminal.clear();
      }

      // Auth runs via the HttpOnly access_token_cookie, which the browser
      // sends automatically with the WebSocket handshake on same-origin.
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : "";

      const wsUrl = `${protocol}//${host}${port}/api/containers/${this.containerId}/exec?shell=${this.selectedShell}`;

      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        this.isConnected = true;
        this.terminal.write(
          "\r\n\x1b[32mConnected to " + this.containerName + "\x1b[0m\r\n"
        );
        this.fit();
        this.terminal.focus();
      };

      this.websocket.onmessage = event => {
        // Attempt to parse JSON only for error handling
        let isJsonError = false;
        try {
          if (
            typeof event.data === "string" &&
            event.data.trim().startsWith("{")
          ) {
            const data = JSON.parse(event.data);
            if (data.error) {
              isJsonError = true;
              if (this.$toast) this.$toast.error(`Shell error: ${data.error}`);
              this.websocket.close();
              return;
            }
          }
        } catch (e) {
          // Not JSON or parse error, treat as terminal output
        }

        if (isJsonError) return;

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

      this.websocket.onclose = event => {
        this.isConnected = false;
        // Check if terminal still exists before writing
        if (this.terminal) {
          this.terminal.write(
            `\r\n\x1b[31mConnection lost (Code: ${event.code})\x1b[0m\r\n`
          );
        }

        if (event.code === 1008) {
          if (this.$toast)
            this.$toast.error(
              "Unauthorized: Session expired. Please log in again."
            );
        } else if (event.code === 1003) {
          if (this.$toast)
            this.$toast.warning(
              `Connection closed: ${event.reason || "Container not available"}`
            );
        } else if (event.code === 1011) {
          if (this.$toast) this.$toast.error("Internal server error.");
        }
      };

      this.websocket.onerror = error => {
        console.error("WebSocket error:", error);
        if (this.terminal) {
          this.terminal.write("\r\n\x1b[31mConnection Error\x1b[0m\r\n");
        }
        if (this.$toast)
          this.$toast.error(
            "WebSocket connection error. Check if container is running."
          );
      };

      // 4. Register new listener and store the disposable
      if (this.terminal) {
        this.dataDisposable = this.terminal.onData(data => {
          // Local echo is disabled. Data is sent to backend.
          if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(data);
          }
        });
      }
    },
    fit() {
      if (this.fitAddon && this.terminal) {
        try {
          this.fitAddon.fit();
          this.sendResize({
            cols: this.terminal.cols,
            rows: this.terminal.rows
          });
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
        this.websocket.send(
          JSON.stringify({
            type: "resize",
            cols: size.cols,
            rows: size.rows
          })
        );
      }
    },
    reconnect() {
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
      if (this.dataDisposable) {
        this.dataDisposable.dispose();
        this.dataDisposable = null;
      }
      if (this.terminal) {
        // Remove context menu listener
        if (this.$refs.terminal) {
          this.$refs.terminal.removeEventListener(
            "contextmenu",
            this.handleContextPaste
          );
        }
        this.terminal.dispose();
        this.terminal = null;
      }
      if (this.copyTimeout) {
        clearTimeout(this.copyTimeout);
      }
      window.removeEventListener("resize", this.handleResize);
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
