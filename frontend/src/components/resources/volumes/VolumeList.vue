<template lang="html">
  <div class="volumes-list component" style="width: 100%">
    <v-card color="foreground">
      <v-fade-transition>
        <v-progress-linear
          indeterminate
          v-if="isLoading"
          color="primary"
          location="bottom"
        />
      </v-fade-transition>
      <v-card-title class="primary font-weight-bold d-flex flex-wrap ga-2">
        Volumes
        <v-dialog v-model="createDialog" max-width="290">
          <template v-slot:activator="{ props }">
            <v-btn class="ml-2" color="secondary" v-bind="props" aria-label="Create volume" title="Create volume">
              <v-icon>mdi-plus</v-icon>
            </v-btn>
            <!-- Prune sits next to the create button so it mirrors the
                 layout used on the Images and Networks pages. Wired to
                 the same /api/settings/prune/<resource> backend route as
                 those, so no new API work is needed. -->
            <v-btn
              class="ml-2"
              color="warning"
              :loading="pruning"
              :disabled="pruning"
              @click="pruneDialog = true"
              aria-label="Prune unused volumes"
              title="Prune unused volumes"
            >
              <v-icon>mdi-broom</v-icon>
            </v-btn>
          </template>
          <v-card color="foreground">
            <v-card-title class="headline" style="word-break: break-all;">
              Create Volume
            </v-card-title>
            <v-card-text>
              Create a Volume.
            </v-card-text>
            <form ref="form" @submit.prevent="submit">
              <v-text-field
                label="Volume"
                class="mx-5"
                placeholder="yacht_data"
                required
                v-model="form.name"
              >
              </v-text-field>
            </form>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="createDialog = false">
                Cancel
              </v-btn>
              <v-btn
                variant="text"
                color="primary"
                :loading="creating"
                :disabled="creating || !form.name.trim()"
                @click="submit"
              >
                Create
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
        <v-spacer />
        <v-text-field
          v-model="search"
          append-icon="mdi-magnify"
          label="Search"
          single-line
          hide-details
        ></v-text-field>
      </v-card-title>

      <v-data-table
        style="max-width: 99%;"
        class="mx-auto volume-datatable foreground"
        :headers="headers"
        :items="volumes"
        :loading="isLoading"
        loading-text="Loading volumes..."
        :items-per-page="25"
        :items-per-page-options="[15, 25, 50, -1]"
        :search="search"
        @click:row="handleRowClick"
      >
        <template #no-data>
          <div>
            No Volumes available.
          </div>
        </template>
        <template v-slot:item.Name="{ item }">
          <div class="d-flex">
            <span class="align-streatch text-truncate nametext mt-2">{{
              item.Name
            }}</span>
            <v-spacer />

            <v-chip
              variant="outlined"
              size="small"
              color="orange lighten-1"
              class="align-center mt-1"
              label
              v-if="item.inUse == false"
              >Unused</v-chip
            >
            <v-menu close-on-click close-on-content-click>
              <template v-slot:activator="{ props }">
                <v-btn
                  icon
                  class="align-streatch"
                  size="small"
                  v-bind="props"
                  @click.stop
                  :aria-label="`Actions for ${item.Name}`"
                >
                  <v-icon>mdi-dots-horizontal</v-icon>
                </v-btn>
              </template>
              <v-list color="foreground" density="compact">
                <v-list-item @click="volumeDetails(item.Name)">
                  <span>
                    <v-icon>mdi-eye</v-icon>
                  </span>
                  <v-list-item-title>View</v-list-item-title>
                </v-list-item>
                <v-divider />
                <v-list-item
                  @click="
                    selectedVolume = item;
                    deleteDialog = true;
                  "
                >
                  <span>
                    <v-icon>mdi-delete</v-icon>
                  </span>
                  <v-list-item-title>Delete</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </div>
        </template>
        <template v-slot:item.Project="{ item }">
          <div class="projectcell">
            <span
              class="d-inline-block text-truncate idtext"
              v-if="item.Labels"
            >
              {{ item.Labels["com.docker.compose.project"] || "-" }}
            </span>
          </div>
        </template>
        <template v-slot:item.Driver="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.Driver }}
            </span>
          </div>
        </template>
        <template v-slot:item.CreatedAt="{ item }">
          <span
            class="d-inline-block text-truncate flex-grow-1 flex-shrink-0"
            >{{ $formatDate(item.CreatedAt) }}</span
          >
        </template>
      </v-data-table>
    </v-card>

    <!-- Prune confirm dialog: volume pruning is destructive — every
         unused volume on the host gets deleted, including ones from
         other docker-compose projects on the same host. Make the user
         confirm explicitly. -->
    <v-dialog v-model="pruneDialog" max-width="380">
      <v-card color="foreground">
        <v-card-title class="headline">Prune unused volumes?</v-card-title>
        <v-card-text>
          This will permanently delete every volume that is not currently
          attached to a container — including dangling volumes from other
          projects on this host. Data inside those volumes cannot be
          recovered.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="pruneDialog = false">Cancel</v-btn>
          <v-btn
            variant="text"
            color="warning"
            :loading="pruning"
            :disabled="pruning"
            @click="pruneVolumes"
          >
            Prune
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-if="selectedVolume" v-model="deleteDialog" max-width="290">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Delete the volume?
        </v-card-title>
        <v-card-text>
          Are you sure you want to permanently delete the volume?<br />
          This action cannot be revoked.
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false">
            Cancel
          </v-btn>
          <v-btn
            variant="text"
            color="error"
            :loading="deleting"
            :disabled="deleting"
            @click="confirmDelete"
          >
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from "axios";
import { mapActions, mapState } from "vuex";
export default {
  data() {
    return {
      selectedVolume: null,
      deleteDialog: false,
      deleting: false,
      pruneDialog: false,
      pruning: false,
      form: {
        name: ""
      },
      createDialog: false,
      creating: false,
      search: "",
      headers: [
        {
          title: "Name",
          key: "Name",
          sortable: true
        },
        {
          title: "Project",
          key: "Project",
          sortable: true
        },
        {
          title: "Driver",
          key: "Driver",
          sortable: true
        },
        {
          title: "Created",
          key: "CreatedAt",
          sortable: true
        }
      ]
    };
  },
  methods: {
    async confirmDelete() {
      if (this.deleting) return;
      this.deleting = true;
      try {
        if (await this.deleteVolume(this.selectedVolume.Name)) this.deleteDialog = false;
      } finally {
        this.deleting = false;
      }
    },
    ...mapActions({
      readVolumes: "volumes/readVolumes",
      deleteVolume: "volumes/deleteVolume",
      writeVolume: "volumes/writeVolume"
    }),
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/resources/volumes/${item.Name}` });
    },
    volumeDetails(volumename) {
      this.$router.push({ path: `/resources/volumes/${volumename}` });
    },
    async submit() {
      if (this.creating || !this.form.name.trim()) return;
      this.creating = true;
      try {
        if (await this.writeVolume({ name: this.form.name.trim() })) {
          this.createDialog = false;
          this.form.name = '';
        }
      } finally {
        this.creating = false;
      }
    },
    async pruneVolumes() {
      if (this.pruning) return;
      this.pruning = true;
      try {
        const { data } = await axios.post("/settings/prune/volumes");
        const deleted = data?.VolumesDeleted?.length || 0;
        this.$store.commit("snackbar/setMessage", `${deleted} volumes pruned.`);
        this.pruneDialog = false;
        await this.readVolumes();
      } catch (err) {
        this.$store.commit("snackbar/setErr", err);
      } finally {
        this.pruning = false;
      }
    }
  },
  computed: {
    ...mapState("volumes", ["volumes", "isLoading"])
  },
  mounted() {
    this.readVolumes();
  }
};
</script>

<style lang="css" scoped>
.nametext {
  max-width: 20vw;
}
.idtext {
  max-width: 30vw;
}
.volume-datatable {
  overflow-x: auto;
}
</style>
