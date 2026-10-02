<template lang="html">
  <div class="networks-list component" style="width: 100%">
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
        Networks
        <v-btn
          class="ml-2"
          color="secondary"
          :to="{ path: `/resources/networks/new` }"
          aria-label="Create network"
          title="Create network"
        >
          <v-icon>mdi-plus</v-icon>
        </v-btn>
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn
              class="ml-2"
              color="warning"
              v-bind="props"
              :loading="pruning"
              :disabled="pruning"
              aria-label="Prune unused networks"
              @click="pruneDialog = true"
            >
              <v-icon>mdi-broom</v-icon>
            </v-btn>
          </template>
          <span>Prune Unused Networks</span>
        </v-tooltip>
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
        class="mx-auto network-datatable foreground"
        :headers="headers"
        :items="networks"
        :loading="isLoading"
        loading-text="Loading networks..."
        :items-per-page="25"
        :items-per-page-options="[15, 25, 50, -1]"
        :search="search"
        @click:row="handleRowClick"
      >
        <template #no-data>
          <div>
            No Networks available.
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
                <v-list-item @click="networkDetails(item.Id)">
                  <span>
                    <v-icon>mdi-eye</v-icon>
                  </span>
                  <v-list-item-title>View</v-list-item-title>
                </v-list-item>
                <v-divider />
                <v-list-item
                  @click="
                    selectedNetwork = item;
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
              v-if="item.Project"
            >
              {{ item.Project || "-" }}
            </span>
          </div>
        </template>
        <template v-slot:item.Id="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.Id }}
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
        <template v-slot:item.Created="{ item }">
          <span
            class="d-inline-block text-truncate flex-grow-1 flex-shrink-0"
            >{{ $formatDate(item.Created) }}</span
          >
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="pruneDialog" max-width="420" :persistent="pruning">
      <v-card>
        <v-card-title>Prune unused networks?</v-card-title>
        <v-card-text>Remove every network that is not attached to a container on this Docker host. Other projects may need to recreate their networks.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="pruning" @click="pruneDialog = false">Cancel</v-btn>
          <v-btn color="warning" :loading="pruning" :disabled="pruning" @click="pruneNetworks">Prune</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-if="selectedNetwork" v-model="deleteDialog" max-width="290">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Delete the network?
        </v-card-title>
        <v-card-text>
          Are you sure you want to permanently delete the network?<br />
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
      selectedNetwork: null,
      deleteDialog: false,
      deleting: false,
      pruning: false,
      pruneDialog: false,
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
          title: "ID",
          key: "Id",
          sortable: true
        },
        {
          title: "Driver",
          key: "Driver",
          sortable: true
        },
        {
          title: "Created",
          key: "Created",
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
        if (await this.deleteNetwork(this.selectedNetwork.Id)) this.deleteDialog = false;
      } finally {
        this.deleting = false;
      }
    },
    ...mapActions({
      readNetworks: "networks/readNetworks",
      deleteNetwork: "networks/deleteNetwork",
      writeNetwork: "networks/writeNetwork"
    }),
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/resources/networks/${item.Id}` });
    },
    networkDetails(networkid) {
      this.$router.push({ path: `/resources/networks/${networkid}` });
    },
    async pruneNetworks() {
      if (this.pruning) return;
      this.pruning = true;
      try {
        const { data } = await axios.post('/settings/prune/networks');
        this.$store.commit('snackbar/setMessage', `${data?.NetworksDeleted?.length || 0} networks pruned.`);
        this.pruneDialog = false;
        await this.readNetworks();
      } catch (error) {
        this.$store.commit('snackbar/setErr', error);
      } finally {
        this.pruning = false;
      }
    }
  },
  computed: {
    ...mapState("networks", ["networks", "isLoading"])
  },
  mounted() {
    this.readNetworks();
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
.network-datatable {
  overflow-x: auto;
}
</style>
