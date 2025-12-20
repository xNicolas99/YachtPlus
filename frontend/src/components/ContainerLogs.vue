<template>
  <v-dialog
    v-model="dialog"
    fullscreen
    hide-overlay
    transition="dialog-bottom-transition"
    @keydown.esc="close"
  >
    <v-card class="d-flex flex-column" style="height: 100vh;">
      <v-toolbar dark color="primary" dense flex>
        <v-toolbar-title>{{ containerName }} - Logs</v-toolbar-title>
        <v-spacer></v-spacer>

        <v-tooltip bottom>
          <template v-slot:activator="{ on, attrs }">
            <v-btn icon @click="toggleFollow" v-bind="attrs" v-on="on">
              <v-icon>{{ following ? "mdi-pause" : "mdi-play" }}</v-icon>
            </v-btn>
          </template>
          <span>{{ following ? "Pause Auto-scroll" : "Resume Auto-scroll" }}</span>
        </v-tooltip>

        <v-menu offset-y>
          <template v-slot:activator="{ on, attrs }">
            <v-btn text v-bind="attrs" v-on="on" class="ml-2">
              {{ tailLines }} Lines <v-icon right>mdi-menu-down</v-icon>
            </v-btn>
          </template>
          <v-list>
            <v-list-item
              v-for="lines in [100, 500, 1000, 2000, 5000]"
              :key="lines"
              @click="changeTail(lines)"
            >
              <v-list-item-title>{{ lines }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>

        <v-tooltip bottom>
          <template v-slot:activator="{ on, attrs }">
            <v-btn
              icon
              @click="toggleTimestamps"
              v-bind="attrs"
              v-on="on"
              :color="timestamps ? 'secondary' : ''"
            >
              <v-icon>mdi-clock-outline</v-icon>
            </v-btn>
          </template>
          <span>Toggle Timestamps</span>
        </v-tooltip>

        <v-tooltip bottom>
          <template v-slot:activator="{ on, attrs }">
            <v-btn icon @click="downloadLogs" v-bind="attrs" v-on="on">
              <v-icon>mdi-download</v-icon>
            </v-btn>
          </template>
          <span>Download Logs</span>
        </v-tooltip>

        <v-btn icon @click="close"><v-icon>mdi-close</v-icon></v-btn>
      </v-toolbar>

      <v-card-text class="flex-grow-1 d-flex flex-column pa-0">
        <div class="d-flex align-center pa-2 grey darken-3">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            label="Search logs..."
            hide-details
            dense
            outlined
            dark
            class="mr-2"
          ></v-text-field>
        </div>

        <div
          ref="logsContainer"
          class="logs-output flex-grow-1 pa-4 black white--text"
          style="overflow-y: auto; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap;"
        >
          <div v-if="filteredLogs.length === 0 && logs.length > 0" class="grey--text">
            No logs match your search.
          </div>
          <div v-else-if="logs.length === 0" class="grey--text">
            Waiting for logs...
          </div>
          <div v-for="(line, index) in filteredLogs" :key="index">{{ line }}</div>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
export default {
  props: {
    containerId: {
      type: String,
      required: false
    },
    containerName: {
      type: String,
      default: "Container"
    },
    visible: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      dialog: false,
      logs: [],
      eventSource: null,
      following: true,
      tailLines: 1000,
      timestamps: true,
      searchQuery: "",
      autoScroll: true
    };
  },
  watch: {
    visible(val) {
      this.dialog = val;
      if (val) {
        this.initLogs();
      } else {
        this.closeLogs();
      }
    },
    dialog(val) {
      if (!val) {
        this.$emit("close");
      }
    },
    logs() {
      if (this.following && this.autoScroll) {
        this.$nextTick(() => {
          this.scrollToBottom();
        });
      }
    }
  },
  computed: {
    filteredLogs() {
      if (!this.searchQuery) {
        return this.logs;
      }
      const lowerQuery = this.searchQuery.toLowerCase();
      return this.logs.filter(line => line.toLowerCase().includes(lowerQuery));
    }
  },
  methods: {
    initLogs() {
      this.logs = [];
      this.closeLogs();

      if (!this.containerId) return;

      const url = `/api/containers/${this.containerId}/logs?tail=${this.tailLines}&follow=true&timestamps=${this.timestamps}`;

      this.eventSource = new EventSource(url);

      this.eventSource.onmessage = event => {
        try {
            let data = event.data;
            // Parse JSON if necessary
            if (typeof data === 'string' && data.startsWith('{') && data.includes('"data":')) {
                try {
                    const parsed = JSON.parse(data);
                    if (parsed.data) {
                        data = parsed.data;
                    }
                } catch (e) {
                    // Not JSON or parse failed, use raw
                }
            }
            this.logs.push(data);

            if (this.logs.length > 10000) {
                this.logs.shift();
            }
        } catch (e) {
            console.error("Error parsing log line", e);
        }
      };

      this.eventSource.onerror = err => {
        console.error("EventSource failed:", err);
      };
    },
    closeLogs() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
    },
    close() {
      this.closeLogs();
      this.dialog = false;
    },
    toggleFollow() {
      this.following = !this.following;
      if (this.following) {
        this.scrollToBottom();
      }
    },
    toggleTimestamps() {
      this.timestamps = !this.timestamps;
      this.initLogs();
    },
    changeTail(lines) {
      this.tailLines = lines;
      this.initLogs();
    },
    scrollToBottom() {
      const container = this.$refs.logsContainer;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    },
    downloadLogs() {
      const element = document.createElement("a");
      const file = new Blob([this.logs.join("\n")], { type: "text/plain" });
      element.href = URL.createObjectURL(file);
      element.download = `${this.containerName}_logs.txt`;
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);

      if (this.$toast) {
          this.$toast.success("Logs downloaded");
      }
    }
  },
  beforeDestroy() {
    this.closeLogs();
  }
};
</script>

<style scoped>
.logs-output {
  background-color: #1e1e1e;
  color: #d4d4d4;
  line-height: 1.5;
}
/* Scrollbar styling */
.logs-output::-webkit-scrollbar {
  width: 10px;
}
.logs-output::-webkit-scrollbar-track {
  background: #1e1e1e;
}
.logs-output::-webkit-scrollbar-thumb {
  background: #555;
}
.logs-output::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>
