<template>
  <v-card class="container-card d-flex flex-column fill-height" elevation="2">
    <!-- Header: Status & Actions -->
    <div class="card-header d-flex justify-space-between align-start px-4 pt-4 pb-2">
      <div class="d-flex align-center flex-grow-1" style="min-width: 0;">
        <!-- Status Indicator -->
        <div class="status-indicator mr-3" :class="statusClass">
          <div class="pulse-ring" v-if="statusClass === 'running'"></div>
        </div>

        <div class="text-truncate" style="flex: 1;">
          <h3 class="text-subtitle-1 font-weight-bold text-truncate" :title="container.name">
            {{ container.name }}
          </h3>
          <div class="text-caption text-medium-emphasis text-uppercase font-weight-bold" style="letter-spacing: 0.5px;">
            {{ container.State.Status }}
          </div>
        </div>
      </div>

      <!-- Quick Actions (Hover visible or always visible based on pref? Keep always visible for utility) -->
      <div class="actions d-flex ml-2">
        <v-btn icon size="x-small" variant="text" color="medium-emphasis" @click.stop="$emit('logs', container.name)" title="Logs">
          <v-icon>mdi-file-document-outline</v-icon>
        </v-btn>

        <v-menu location="bottom end">
          <template v-slot:activator="{ props }">
            <v-btn icon size="x-small" variant="text" color="medium-emphasis" v-bind="props">
              <v-icon>mdi-dots-vertical</v-icon>
            </v-btn>
          </template>
          <v-list density="compact" width="150">
            <v-list-item @click="$emit('action', 'restart')" prepend-icon="mdi-restart">
              Restart
            </v-list-item>
            <v-list-item
              @click="$emit('action', container.State.Status === 'running' ? 'stop' : 'start')"
              :prepend-icon="container.State.Status === 'running' ? 'mdi-stop' : 'mdi-play'"
              :color="container.State.Status === 'running' ? 'warning' : 'success'"
            >
              {{ container.State.Status === 'running' ? 'Stop' : 'Start' }}
            </v-list-item>
            <v-divider></v-divider>
            <v-list-item @click="$emit('action', 'remove')" prepend-icon="mdi-delete" color="error">
              Remove
            </v-list-item>
          </v-list>
        </v-menu>
      </div>
    </div>

    <v-divider class="mx-4 opacity-10"></v-divider>

    <!-- Body: Stats -->
    <v-card-text class="flex-grow-1 py-3">
      <div v-if="stats">
        <!-- CPU -->
        <div class="stat-row mb-3">
          <div class="d-flex justify-space-between text-caption mb-1">
            <span class="text-medium-emphasis">CPU</span>
            <span class="font-weight-bold" :class="getUsageColorText(stats.cpu_percent)">
              {{ stats.cpu_percent }}%
            </span>
          </div>
          <v-progress-linear
            :model-value="stats.cpu_percent"
            :color="getUsageColor(stats.cpu_percent)"
            height="6"
            rounded
            bg-color="surface-variant"
            bg-opacity="0.3"
          ></v-progress-linear>
        </div>

        <!-- RAM -->
        <div class="stat-row">
          <div class="d-flex justify-space-between text-caption mb-1">
            <span class="text-medium-emphasis">RAM</span>
            <span class="font-weight-bold" :class="getUsageColorText(stats.mem_percent)">
              {{ stats.mem_percent }}%
            </span>
          </div>
          <v-progress-linear
            :model-value="stats.mem_percent"
            :color="getUsageColor(stats.mem_percent)"
            height="6"
            rounded
            bg-color="surface-variant"
            bg-opacity="0.3"
          ></v-progress-linear>
          <div class="text-right mt-1">
            <span class="text-caption text-disabled" style="font-size: 0.65rem;">
              {{ stats.mem_current }} / {{ stats.mem_total }}
            </span>
          </div>
        </div>
      </div>

      <!-- No Stats / Offline -->
      <div v-else class="d-flex align-center justify-center fill-height flex-column opacity-50 py-2">
        <template v-if="container.State.Status === 'running'">
          <v-progress-circular indeterminate size="20" width="2" color="primary" class="mb-2"></v-progress-circular>
          <span class="text-caption">Loading Stats...</span>
        </template>
        <template v-else>
           <v-icon size="small" class="mb-1">mdi-power-off</v-icon>
           <span class="text-caption">Offline</span>
        </template>
      </div>
    </v-card-text>

    <!-- Footer: Image Info -->
    <div class="card-footer px-4 pb-3 pt-0">
      <div class="d-flex align-center text-caption text-disabled text-truncate">
        <v-icon size="x-small" class="mr-1">mdi-image-outline</v-icon>
        <span class="text-truncate" :title="container.Image">{{ cleanImageName(container.Image) }}</span>
      </div>
    </div>
  </v-card>
</template>

<script>
export default {
  name: "ContainerCard",
  props: {
    container: {
      type: Object,
      required: true
    },
    stats: {
      type: Object,
      default: null
    }
  },
  computed: {
    statusClass() {
      const s = this.container.State.Status.toLowerCase();
      if (s === 'running') return 'running';
      if (s === 'exited' || s === 'stopped') return 'stopped';
      if (s === 'restarting') return 'warning';
      return 'default';
    }
  },
  methods: {
    cleanImageName(img) {
      if (!img) return 'Unknown';
      // Remove sha256 or tag if too long? For now just return
      return img.split('@')[0];
    },
    getUsageColor(percent) {
        if (percent < 50) return 'success';
        if (percent < 80) return 'warning';
        return 'error';
    },
    getUsageColorText(percent) {
        if (percent < 50) return 'text-success';
        if (percent < 80) return 'text-warning';
        return 'text-error';
    }
  }
};
</script>

<style scoped>
.container-card {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgb(var(--v-theme-surface));
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  overflow: visible; /* For menu/tooltips */
}

.container-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.2) !important;
  border-color: rgba(var(--v-theme-primary), 0.5);
  z-index: 1;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  position: relative;
}

.status-indicator.running { background-color: rgb(var(--v-theme-success)); box-shadow: 0 0 8px rgba(var(--v-theme-success), 0.6); }
.status-indicator.stopped { background-color: rgb(var(--v-theme-medium-emphasis)); }
.status-indicator.warning { background-color: rgb(var(--v-theme-warning)); }
.status-indicator.default { background-color: rgb(var(--v-theme-grey)); }

.pulse-ring {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 100%; height: 100%;
  border-radius: 50%;
  border: 2px solid rgb(var(--v-theme-success));
  animation: pulse 2s infinite;
  opacity: 0;
}

@keyframes pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.8; }
  100% { transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
}
</style>
