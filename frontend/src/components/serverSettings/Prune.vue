<template>
  <v-card color="foreground">
    <v-progress-linear v-if="isLoading" indeterminate color="primary" />
    <v-card-title class="font-weight-bold">Prune unused resources</v-card-title>
    <v-card-text>Remove resources from this Docker host. Review the confirmation before continuing.</v-card-text>
    <v-btn
      v-for="resource in resources"
      :key="resource.key"
      class="mx-5 mb-5"
      color="warning"
      :loading="loadingResource === resource.key"
      :disabled="isLoading"
      @click="selectedResource = resource"
    >Prune {{ resource.label }}</v-btn>
    <v-dialog :model-value="!!selectedResource" @update:model-value="!$event && (selectedResource = null)" :persistent="isLoading" max-width="440">
      <v-card v-if="selectedResource">
        <v-card-title>Prune {{ selectedResource.label.toLowerCase() }}?</v-card-title>
        <v-card-text>{{ selectedResource.warning }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="isLoading" @click="selectedResource = null">Cancel</v-btn>
          <v-btn color="error" :loading="isLoading" :disabled="isLoading" @click="prune(selectedResource.key)">Prune</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import axios from "axios";
import { mapMutations } from "vuex";
export default {
  data() {
    return {
      selectedResource: null,
      isLoading: false,
      loadingResource: null,
      resources: [
        { key: 'images', label: 'Images', warning: 'Remove all images that are not referenced by a container. Images needed later must be downloaded again.' },
        { key: 'networks', label: 'Networks', warning: 'Remove networks that are not attached to a container. Other projects may need to recreate them.' },
        { key: 'volumes', label: 'Volumes', warning: 'Permanently remove unused volumes on this Docker host. Their data cannot be recovered. This can affect other projects.' },
        { key: 'containers', label: 'Containers', warning: 'Permanently remove all stopped containers on this Docker host, including files in their writable layers.' },
      ],
    };
  },
  methods: {
    ...mapMutations({ setMessage: 'snackbar/setMessage', setErr: 'snackbar/setErr' }),
    formatBytes(bytes = 0) {
      if (!Number.isFinite(bytes) || bytes <= 0) return '0 Bytes';
      const units = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
      const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
      return `${Number((bytes / 1024 ** index).toFixed(2))} ${units[index]}`;
    },
    async prune(resource) {
      if (this.isLoading) return;
      this.isLoading = true;
      this.loadingResource = resource;
      try {
        const { data } = await axios.post(`/settings/prune/${resource}`);
        const key = { images: 'ImagesDeleted', networks: 'NetworksDeleted', volumes: 'VolumesDeleted', containers: 'ContainersDeleted' }[resource];
        const deleted = resource === 'images'
          ? new Set((data?.ImagesDeleted || []).map(item => item.Deleted).filter(Boolean)).size
          : data?.[key]?.length || 0;
        this.setMessage(`${deleted} ${resource} pruned. Space reclaimed: ${this.formatBytes(data?.SpaceReclaimed)}.`);
        this.selectedResource = null;
      } catch (error) {
        this.setErr(error);
      } finally {
        this.isLoading = false;
        this.loadingResource = null;
      }
    },
  },
};
</script>
