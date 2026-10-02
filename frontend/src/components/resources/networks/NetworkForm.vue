<template lang="html">
  <div class="networks-list component" style="max-width: 90%">
    <v-card color="foreground">
      <Form ref="general" v-slot="{ meta }" @submit="submit">
        <v-fade-transition>
          <v-progress-linear
            indeterminate
            v-if="isLoading"
            color="primary"
            bottom
          />
        </v-fade-transition>

        <v-card-title class="headline" style="word-break: break-all;">
          Create Network
        </v-card-title>
        <v-card-text>
          Create a new Network.
        </v-card-text>
          <v-card-text>
            General
          </v-card-text>

          <Field
            name="Name"
            v-model="form.name"
            rules="required"
            v-slot="{ componentField, errors }"
          >
            <v-text-field
              label="Name *"
              class="mx-7"
              placeholder="yacht_network"
              :error-messages="errors"
              required
              v-bind="componentField"
            />
          </Field>
          <Field
            name="Driver"
            v-model="form.networkDriver"
            rules="required"
            v-slot="{ componentField, errors }"
          >
            <v-select
              class="mx-7"
              label="Driver *"
              placeholder="bridge"
              :error-messages="errors"
              :items="network_drivers"
              v-bind="componentField"
            />
          </Field>
          <Field
            v-if="form.networkDriver == 'macvlan'"
            name="Network Interface"
            v-model="form.network_devices"
            rules="required"
            v-slot="{ componentField, errors }"
          >
            <v-text-field
              class="mx-7"
              label="Network Interface *"
              placeholder="eth0"
              :error-messages="errors"
              v-bind="componentField"
            />
          </Field>
          <v-row class="mx-5">
            <v-col>
              <v-checkbox v-model="form.internal" label="Internal Only" />
            </v-col>
            <v-col>
              <v-checkbox v-model="form.attachable" label="Attachable" />
            </v-col>
            <v-col>
              <v-checkbox v-model="form.ipv6_enabled" label="Enable IPv6" />
            </v-col>
          </v-row>
          <div
            v-if="
              form.networkDriver == 'bridge' ||
                form.networkDriver == 'macvlan' ||
                form.networkDriver == 'ipvlan'
            "
          >
            <v-card-text> IPv4 </v-card-text>
            <v-row class="mx-5">
              <v-col>
                <v-text-field
                  label="Subnet"
                  placeholder="10.0.200.0/24"
                  v-model="form.ipv4subnet"
                />
              </v-col>
              <v-col>
                <v-text-field
                  label="Gateway"
                  placeholder="10.0.200.1"
                  v-model="form.ipv4gateway"
                />
              </v-col>
            </v-row>
            <v-row class="mx-5">
              <v-col>
                <v-text-field
                  v-if="form.networkDriver != 'macvlan'"
                  label="IP Range"
                  placeholder="10.0.200.0/24"
                  v-model="form.ipv4range"
                />
              </v-col>
            </v-row>
          </div>
          <div
            v-if="
              form.networkDriver == 'bridge' || form.networkDriver == 'macvlan'
            "
          >
            <v-card-text> IPv6 </v-card-text>
            <v-row class="mx-5">
              <v-col>
                <v-text-field
                  label="Subnet"
                  placeholder="2001:db8::/32"
                  v-model="form.ipv6subnet"
                  :disabled="!form.ipv6_enabled"
                />
              </v-col>
              <v-col>
                <v-text-field
                  label="Gateway"
                  placeholder="2001:db8::1"
                  v-model="form.ipv6gateway"
                  :disabled="!form.ipv6_enabled"
                />
              </v-col>
            </v-row>
            <v-row class="mx-5">
              <v-col>
                <v-text-field
                  v-if="form.networkDriver != 'macvlan'"
                  label="IP Range"
                  placeholder="2001:db8::1"
                  v-model="form.ipv6range"
                  :disabled="!form.ipv6_enabled"
                />
              </v-col>
            </v-row>
          </div>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="isLoading" @click="$router.push({ name: 'Networks' })">
            Cancel
          </v-btn>
          <v-btn
            variant="text"
            color="primary"
            type="submit"
            :loading="isLoading"
            :disabled="!meta.valid || isLoading"
          >
            Create
          </v-btn>
        </v-card-actions>
      </Form>
    </v-card>
  </div>
</template>

<script>
import { Form, Field } from "vee-validate";
import axios from "axios";
import { mapMutations } from "vuex";

export default {
  components: {
    Field,
    Form
  },
  data() {
    return {
      selectedNetwork: null,
      deleteDialog: false,
      form: {
        name: "",
        networkDriver: "",
        internal: false,
        attachable: true,
        network_devices: "",
        ipv4subnet: "",
        ipv4gateway: "",
        ipv4range: "",
        ipv6subnet: "",
        ipv6gateway: "",
        ipv6range: "",
        ipv6_enabled: false
      },
      createDialog: false,
      search: "",
      isLoading: false,
      network_drivers: ["bridge", "macvlan", "ipvlan"],
      network_devices: [],
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
    ...mapMutations({
      setErr: "snackbar/setErr"
    }),
    async submit() {
      if (this.isLoading) return;
      const payload = { ...this.form };
      this.isLoading = true;
      try {
        await axios.post("/resources/networks/", payload);
        await this.$router.push({ name: "Networks" });
      } catch (err) {
        this.setErr(err);
      } finally {
        this.isLoading = false;
      }
    }
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
  overflow-x: hidden;
}
</style>
