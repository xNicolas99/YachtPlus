<template>
  <div v-if="network" class="page">
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
            <v-btn icon size="small" v-bind="props" aria-label="Network Actions" title="Network Actions">
              <v-icon>mdi-chevron-down</v-icon>
            </v-btn>
          </template>
          <v-list color="foreground" density="compact">
            <v-list-item
              :disabled="deleting"
              @click="deleteDialog = true"
            >
              <span
                ><v-icon>mdi-trash-can-outline</v-icon></span
              >
              <v-list-item-title>Delete Network</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        {{ network.Name }}
      </v-card-title>
      <v-card-subtitle>
        <v-chip
          variant="outlined"
          size="small"
          color="orange lighten-1"
          class="align-center mt-1"
          label
          v-if="network.inUse == false"
          >Unused</v-chip
        >
        {{ network.Id }}
      </v-card-subtitle>
    </v-card>
    <v-card color="foreground" class="mt-2">
      <v-card-title>
        Network Information
      </v-card-title>
      <v-list color="foreground" density="compact">
        <v-list-item>
          <div>
            Name
          </div>
          <div>
            {{ network.Name }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            ID
          </div>
          <div>
            {{ network.Id }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Driver
          </div>
          <div>
            {{ network.Driver }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Scope
          </div>
          <div>
            {{ network.Scope }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Attachable
          </div>
          <div>
            {{ network.Attachable }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Internal
          </div>
          <div>
            {{ network.Internal }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            IPV6 Enabled
          </div>
          <div>
            {{ network.EnableIPv6 }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Created
          </div>
          <div>
            {{ $formatDate(network.Created) }}
          </div>
        </v-list-item>
        <v-list-item v-if="Object.keys(network.Labels || {}).length > 0">
          <div>
            Labels
          </div>
          <div>
            <v-card variant="outlined" rounded="0">
              <v-table class="foreground" density="compact">
                <tbody>
                  <tr
                    v-for="(value, key, index) in network.Labels"
                    :key="index"
                  >
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

    <v-card color="foreground" class="mt-2">
      <v-card-title>
        Network Details
      </v-card-title>
      <v-list color="foreground" density="compact">
        <v-list-item>
          <div style="max-width: 30%">
            IPV4 Subnet
          </div>
          <div>
            {{ ipv4Config.Subnet || "-" }}
          </div>
        </v-list-item>
        <v-list-item>
          <div style="max-width: 30%">
            IPV4 Gateway
          </div>
          <div>
            {{ ipv4Config.Gateway || "-" }}
          </div>
        </v-list-item>
        <v-list-item>
          <div style="max-width: 30%">
            IPV6 Subnet
          </div>
          <div>
            -
          </div>
        </v-list-item>
        <v-list-item>
          <div style="max-width: 30%">
            IPv6 Gateway
          </div>
          <div>
            -
          </div>
        </v-list-item>
        <v-list-item v-if="Object.keys(network.Options || {}).length > 0">
          <div style="max-width: 30%">
            Options
          </div>
          <div>
            <v-card variant="outlined" rounded="0">
              <v-table density="compact">
                <tbody>
                  <tr
                    v-for="(value, key, index) in network.Options"
                    :key="index"
                  >
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

    <v-card color="foreground" class="mt-2">
      <v-card-title>
        Attached Containers
      </v-card-title>
      <v-data-table
        style="max-width: 99%;"
        class="mx-auto network-datatable foreground"
        :headers="headers"
        :items="conv2array(network.Containers)"
        @click:row="handleRowClick"
      >
        <template #no-data>
          <div>
            No containers attached.
          </div>
        </template>
        <template v-slot:item.Name="{ item }">
          <div class="d-flex">
            <span class="align-streatch text-truncate nametext mt-2">
              {{ item.Name }}</span
            >
          </div>
        </template>
        <template v-slot:item.ipv4="{ item }">
          <div class="projectcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.IPv4Address || "-" }}
            </span>
          </div>
        </template>
        <template v-slot:item.ipv6="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.IPv6Address || "-" }}
            </span>
          </div>
        </template>
        <template v-slot:item.macaddress="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.MacAddress }}
            </span>
          </div>
        </template>
        <template v-slot:item.ID="{ item }">
          <span
            class="d-inline-block text-truncate flex-grow-1 flex-shrink-0"
            >{{ item.EndpointID }}</span
          >
        </template>
      </v-data-table>
    </v-card>
    <v-dialog v-model="deleteDialog" max-width="420" :persistent="deleting">
      <v-card>
        <v-card-title>Delete the network?</v-card-title>
        <v-card-text>
          Permanently delete {{ network.Name }}? This action cannot be revoked.
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
  <v-alert v-else type="error">Network details are unavailable.</v-alert>
</template>

<script>
import { mapActions, mapGetters, mapState } from "vuex";

export default {
  data() {
    return {
      deleteDialog: false,
      deleting: false,
      headers: [
        {
          title: "Name",
          key: "Name",
          sortable: true
        },
        {
          title: "IPv4",
          key: "ipv4",
          sortable: true
        },
        {
          title: "IPv6",
          key: "ipv6",
          sortable: true
        },
        {
          title: "MacAddress",
          key: "macaddress",
          sortable: true
        },
        {
          title: "ID",
          key: "ID",
          sortable: true
        }
      ]
    };
  },
  computed: {
    ...mapState("networks", ["isLoading"]),
    ...mapGetters({
      getNetworkById: "networks/getNetworkById"
    }),
    network() {
      const networkid = this.$route.params.networkid;
      return this.getNetworkById(networkid);
    },
    ipv4Config() {
      return this.network?.IPAM?.Config?.[0] || {};
    }
  },
  methods: {
    ...mapActions({
      readNetwork: "networks/readNetwork",
      deleteNetwork: "networks/deleteNetwork"
    }),
    conv2array(containers) {
      return Object.values(containers || {});
    },
    async confirmDelete() {
      if (this.deleting || !this.deleteDialog || !this.network) return;
      this.deleting = true;
      try {
        if (await this.deleteNetwork(this.network.Id)) {
          this.deleteDialog = false;
          await this.$router.push({ name: "Networks" });
        }
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally {
        this.deleting = false;
      }
    },
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/apps/${encodeURIComponent(item.Name.replace(/^\//, ''))}/info` });
    }
  },
  created() {
    const networkid = this.$route.params.networkid;
    this.readNetwork(networkid);
  }
};
</script>

<style scoped></style>
