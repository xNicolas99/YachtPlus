<template>
  <div v-if="volume" class="page">
    <v-card color="foreground">
      <v-fade-transition>
        <v-progress-linear
          indeterminate
          v-if="isLoading"
          color="primary"
          location="bottom"
        />
      </v-fade-transition>
      <v-card-title>
        <v-menu close-on-click close-on-content-click location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn icon size="small" v-bind="props" aria-label="Volume Actions" title="Volume Actions">
              <v-icon>mdi-chevron-down</v-icon>
            </v-btn>
          </template>
          <v-list color="foreground" density="compact">
            <v-list-item :disabled="deleting" @click="deleteDialog = true">
              <span
                ><v-icon>mdi-trash-can-outline</v-icon></span
              >
              <v-list-item-title>Delete Volume</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        {{ volume.Name }}
      </v-card-title>
      <v-card-subtitle>
        <v-chip
          variant="outlined"
          size="small"
          color="orange lighten-1"
          class="align-center mt-1"
          label
          v-if="volume.inUse == false"
          >Unused</v-chip
        >
      </v-card-subtitle>
    </v-card>
    <v-card color="foreground" class="mt-2">
      <v-card-title>
        Volume Details
      </v-card-title>
      <v-list color="foreground" density="compact">
        <v-list-item>
          <div>
            Name
          </div>
          <div>
            {{ volume.Name }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Driver
          </div>
          <div>
            {{ volume.Driver }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Mountpoint
          </div>
          <div>
            {{ volume.Mountpoint }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Scope
          </div>
          <div>
            {{ volume.Scope }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Created
          </div>
          <div>
            {{ $formatDate(volume.CreatedAt) }}
          </div>
        </v-list-item>
        <v-list-item v-if="volume.Labels">
          <div style="max-width:20%">
            Labels
          </div>
          <div>
            <v-card variant="outlined" rounded="0">
              <v-table density="compact">
                <tbody>
                  <tr v-for="(value, key, index) in volume.Labels" :key="index">
                    <td style="min-width:20%;" class="align-self-center">
                      {{ key }}
                    </td>
                    <td
                      class="text-truncate align-self-center"
                      style="width:100%"
                    >
                      {{ value }}
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </div>
        </v-list-item>
      </v-list>
    </v-card>
    <v-dialog v-model="deleteDialog" max-width="420" :persistent="deleting">
      <v-card>
        <v-card-title>Delete the volume?</v-card-title>
        <v-card-text>
          Permanently delete {{ volume.Name }} and its data?
          This action cannot be revoked.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="deleting" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :loading="deleting" :disabled="deleting" @click="confirmDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
  <v-progress-linear v-else-if="isLoading" indeterminate color="primary" />
  <v-alert v-else type="error">Volume details are unavailable.</v-alert>
</template>

<script>
import { mapActions, mapGetters, mapState } from "vuex";

export default {
  data() {
    return { deleteDialog: false, deleting: false };
  },
  computed: {
    ...mapState("volumes", ["isLoading"]),
    ...mapGetters({
      getVolumeByName: "volumes/getVolumeByName"
    }),
    volume() {
      const volumeName = this.$route.params.volumeName;
      return this.getVolumeByName(volumeName);
    }
  },
  methods: {
    ...mapActions({
      readVolume: "volumes/readVolume",
      deleteVolume: "volumes/deleteVolume"
    }),
    async confirmDelete() {
      if (this.deleting || !this.deleteDialog || !this.volume) return;
      this.deleting = true;
      try {
        if (await this.deleteVolume(this.volume.Name)) {
          this.deleteDialog = false;
          await this.$router.push({ name: "Volumes" });
        }
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally {
        this.deleting = false;
      }
    }
  },
  created() {
    const volumeName = this.$route.params.volumeName;
    this.readVolume(volumeName);
  }
};
</script>

<style scoped></style>
