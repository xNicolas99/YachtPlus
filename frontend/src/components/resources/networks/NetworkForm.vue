<template lang="html">
  <div class="networks-list component" style="max-width: 90%">
    <v-card color="foreground">
      <Form ref="general" v-slot="{ invalid }">
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
        <form ref="form" @submit.prevent="submit">
          <v-card-text>
            General
          </v-card-text>

          <Field v-bind="field"
            name="Name"
            rules="required"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-text-field
              label="Name *"
              class="mx-7"
              placeholder="yacht_network"
              :error-messages="errors"
              :success="fieldMeta.valid"
              required
              v-bind="field"
            />
          </Field>
          <Field v-bind="field"
            name="Driver"
            rules="required"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-select
              class="mx-7"
              label="Driver *"
              placeholder="bridge"
              :error-messages="errors"
              :success="fieldMeta.valid"
              :items="network_drivers"
              v-bind="field"
            />
          </Field>
          <Field v-bind="field"
            name="Network Interface"
            rules="required"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-if="form.networkDriver == 'macvlan'"
              class="mx-7"
              label="Network Interface *"
              placeholder="eth0"
              :error-messages="errors"
              :success="fieldMeta.valid"
              v-bind="field"
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
                <!-- <Field v-bind="field"
                  name="IPv4 Subnet"
                  v-slot="{ field, errors, meta: fieldMeta }"
                > -->
                <v-text-field
                  label="Subnet"
                  placeholder="10.0.200.0/24"
                  v-bind="field"
                />
                <!-- </Field> -->
              </v-col>
              <v-col>
                <!-- <Field v-bind="field"
                  name="IPv4 Gateway"
                  v-slot="{ field, errors, meta: fieldMeta }"
                > -->
                <v-text-field
                  label="Gateway"
                  placeholder="10.0.200.1"
                  v-bind="field"
                />
                <!-- </Field> -->
              </v-col>
            </v-row>
            <v-row class="mx-5">
              <v-col>
                <!-- <Field v-bind="field" name="IP Range" v-slot="{ field, errors, meta: fieldMeta }"> -->
                <v-text-field
                  v-if="form.networkDriver != 'macvlan'"
                  label="IP Range"
                  placeholder="10.0.200.0/24"
                  v-bind="field"
                />
                <!-- </Field> -->
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
                <!-- <Field v-bind="field"
                  name="IPv6 Subnet"
                  v-slot="{ field, errors, meta: fieldMeta }"
                > -->
                <v-text-field
                  label="Subnet"
                  placeholder="2001:db8::/32"
                  v-bind="field"
                  :disabled="!form.ipv6_enabled"
                />
                <!-- </Field> -->
              </v-col>
              <v-col>
                <!-- <Field v-bind="field"
                  name="IPv6 Gateway"
                  v-slot="{ field, errors, meta: fieldMeta }"
                > -->
                <v-text-field
                  label="Gateway"
                  placeholder="2001:db8::1"
                  v-bind="field"
                  :disabled="!form.ipv6_enabled"
                />
                <!-- </Field> -->
              </v-col>
            </v-row>
            <v-row class="mx-5">
              <v-col>
                <!-- <Field v-bind="field"
                  name="IPv6 Gateway"
                  v-slot="{ field, errors, meta: fieldMeta }"
                > -->
                <v-text-field
                  v-if="form.networkDriver != 'macvlan'"
                  label="IP Range"
                  placeholder="2001:db8::1"
                  v-bind="field"
                  :disabled="!form.ipv6_enabled"
                />
                <!-- </Field> -->
              </v-col>
            </v-row>
          </div>
        </form>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="createDialog = false">
            Cancel
          </v-btn>
          <v-btn
            text
            color="primary"
            :disabled="!meta.valid"
            @click="
              submit();
              createDialog = false;
            "
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
          text: "Name",
          value: "Name",
          sortable: true
        },
        {
          text: "Project",
          value: "Project",
          sortable: true
        },
        {
          text: "ID",
          value: "Id",
          sortable: true
        },
        {
          text: "Driver",
          value: "Driver",
          sortable: true
        },
        {
          text: "Created",
          value: "Created",
          sortable: true
        }
      ]
    };
  },
  methods: {
    ...mapMutations({
      setErr: "snackbar/setErr"
    }),
    submit() {
      const payload = { ...this.form };
      this.isLoading = true;
      const url = `/api/resources/networks/`;
      axios
        .post(url, payload)
        .then(() => {
          this.isLoading = false;
          this.$router.push({ name: "Networks" });
        })
        .catch(err => {
          this.isLoading = false;
          this.setErr(err);
        });
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
