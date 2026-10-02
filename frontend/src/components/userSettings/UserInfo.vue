<template>
  <v-card color="foreground" class="elevation-12 pb-8">
    <v-toolbar color="primary" dark flat>
      <v-toolbar-title>User Settings</v-toolbar-title>
      <v-spacer></v-spacer>
    </v-toolbar>
    <v-progress-linear indeterminate v-if="isLoading" />
    <v-card-text>
      This is where you can change settings related to your user account.
    </v-card-text>
    <h2 class="font-weight-bold ml-5">
      API Keys
      <v-dialog id="keyModal" v-model="keyDialog" max-width="500">
        <template v-slot:activator="{ props }">
          <v-btn color="primary" v-bind="props">
            <v-icon>mdi-plus</v-icon>
          </v-btn>
        </template>
        <v-card>
          <v-card-title class="primary">
            Generate API Key
          </v-card-title>
          <v-card-text>
            API Keys should be treated as a password and should only be provided
            to applications you trust. Once this box is closed you will be
            unable to retrive this key so be sure to copy it and test your
            application first.
            <br />
            <v-form>
              <v-text-field
                v-if="!newKey"
                v-model="keyForm.key_name"
                label="Name"
              >
              </v-text-field>
            </v-form>
            <v-alert v-if="error" type="error" class="my-2">{{ error }}</v-alert>
            <v-btn
              v-if="!newKey"
              class="primary"
              @click="generate_api_key()"
              :loading="isGenerating"
              :disabled="isGenerating"
            >
              Generate Key
            </v-btn>
            <br v-if="newKey" />
            <span v-if="newKey" class="font-weight-bold">
              Generated API Key:</span
            >
            <v-btn
              @click="copykey"
              icon
              v-if="newKey"
              aria-label="Copy API Key"
              title="Copy API Key"
              ><v-icon>mdi-clipboard-text-outline</v-icon></v-btn
            >
            <v-textarea
              @click="copykey"
              shaped
              variant="outlined"
              density="compact"
              readonly
              no-resize
              v-if="newKey"
              v-model="newKey"
              id="newapikey"
            ></v-textarea>
            <v-snackbar v-model="saved" bottom color="secondary">
              Copied to clipboard
              <template v-slot:action="{ props }">
                <v-btn
                  color="primary"
                  variant="text"
                  v-bind="props"
                  @click="saved = false"
                >
                  Close
                </v-btn>
              </template>
            </v-snackbar>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn
              @click="
                keyDialog = false;
                newKey = '';
                keyForm.key_name = '';
              "
            >
              Close
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </h2>
    <v-alert v-if="error && !keyDialog" type="error" class="mx-4">{{ error }}</v-alert>
    <v-data-table density="compact" :headers="headers" :items="apiKeys" :items-per-page="5">
      <template v-slot:item.key_name="{ item }">
        <v-btn @click="revoke_api_key(item)" icon aria-label="Revoke API key" title="Revoke API key"
          ><v-icon>mdi-trash-can-outline</v-icon></v-btn
        >
        <span class="ml-2"> {{ item.key_name }} </span>
      </template>
      <template v-slot:item.created_at="{ item }">
          <span class="CreatedAt"> {{ $formatDate(item.created_at) }} </span>
      </template>
    </v-data-table>
  </v-card>
</template>

<script>
import axios from "axios";
export default {
  data() {
    return {
      importFile: null,
      isLoading: false,
      keyDialog: false,
      newKey: null,
      keyForm: {
        key_name: ""
      },
      saved: false,
      isGenerating: false,
      error: null,
      apiKeys: [],
      headers: [
        {
          title: "Name",
          key: "key_name",
          sortable: true,
          align: "start"
        },
        {
          title: "Created Time",
          key: "created_at",
          sortable: true
        }
      ]
    };
  },
  methods: {
    async get_api_keys() {
      try {
        const resp = await axios.get("/auth/api/keys");
        this.apiKeys = Array.isArray(resp.data) ? resp.data : [];
      } catch (err) {
        this.error = "Could not load API keys.";
      }
    },
    async copykey() {
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(this.newKey);
        } else {
          const copytext = document.getElementById("newapikey");
          copytext.select();
          if (!document.execCommand("copy")) throw new Error("Copy failed");
        }
        this.saved = true;
      } catch (err) {
        this.error = "Could not copy the API key. Select the text and copy it manually.";
      }
    },
    async generate_api_key() {
      this.isGenerating = true;
      this.error = null;
      try {
        const resp = await axios.post("/auth/api/keys/new", { ...this.keyForm });
        this.newKey = resp.data.token;
        this.apiKeys.push(resp.data);
      } catch (err) {
        this.error = err.response?.data?.detail || "Could not generate API key.";
      } finally {
        this.isGenerating = false;
      }
    },
    async revoke_api_key(key) {
      this.isLoading = true;
      this.error = null;
      try {
        await axios.delete(`/auth/api/keys/${key.id}`);
        this.apiKeys = this.apiKeys.filter(item => item.id !== key.id);
      } catch (err) {
        this.error = err.response?.data?.detail || "Could not revoke API key.";
      } finally {
        this.isLoading = false;
      }
    }
  },
  async created() {
    await this.get_api_keys();
  }
};
</script>
