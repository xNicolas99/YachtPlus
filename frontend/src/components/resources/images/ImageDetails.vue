<template>
  <div v-if="image" class="page">
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
            <v-btn icon size="small" v-bind="props" aria-label="Image Actions" title="Image Actions">
              <v-icon>mdi-chevron-down</v-icon>
            </v-btn>
          </template>
          <v-list color="foreground" density="compact">
            <v-list-item
              v-if="image.RepoTags?.[0]"
              @click="updateImage(image.Id)"
            >
              <span><v-icon>mdi-update</v-icon></span>
              <v-list-item-title>Pull Image</v-list-item-title>
            </v-list-item>
            <v-list-item :disabled="deleting" @click="deleteDialog = true">
              <span
                ><v-icon>mdi-trash-can-outline</v-icon></span
              >
              <v-list-item-title>Delete Image</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        {{ image.Id }}
      </v-card-title>
      <v-card-subtitle>
        <v-chip
          variant="outlined"
          size="small"
          color="orange lighten-1"
          class="align-center mt-1"
          label
          v-if="image.inUse == false"
          >Unused</v-chip
        >
        {{ image.RepoTags?.[0] || image.RepoDigests?.[0] || "-" }}
      </v-card-subtitle>
    </v-card>
    <v-card color="foreground" class="mt-2">
      <v-card-title>
        Image Details
      </v-card-title>
      <v-list color="foreground" density="compact">
        <v-list-item>
          <div>
            Tag
          </div>
          <div>
            {{ image.RepoTags?.[0] || "-" }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Architecture
          </div>
          <div>
            {{ image.Architecture }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Platform
          </div>
          <div>
            {{ image.Os }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Architecture
          </div>
          <div>
            {{ image.Architecture }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Created
          </div>
          <div>
            {{ $formatDate(image.Created) }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            Size
          </div>
          <div>
            {{ formatBytes(image.Size) }}
          </div>
        </v-list-item>
        <v-list-item>
          <div>
            VirtualSize
          </div>
          <div>
            {{ formatBytes(image.VirtualSize) }}
          </div>
        </v-list-item>
      </v-list>
    </v-card>

    <v-card class="mt-2" color="foreground">
      <v-card-title>
        Container Details
      </v-card-title>
      <v-list density="compact" color="foreground">
        <v-list-item v-if="getCMD(imageConfig.Cmd)">
          <div style="max-width:20%">
            Command
          </div>
          <div>
            {{ getCMD(imageConfig.Cmd) }}
          </div>
        </v-list-item>
        <v-list-item v-if="getCMD(imageConfig.Entrypoint)">
          <div style="max-width:20%">
            Entrypoint
          </div>
          <div>
            {{ getCMD(imageConfig.Entrypoint) }}
          </div>
        </v-list-item>
        <v-list-item v-if="imageConfig.ExposedPorts">
          <div style="max-width:20%">
            Ports
          </div>
          <div
            v-for="(port, index) in Object.keys(
              imageConfig.ExposedPorts
            )"
            :key="index"
          >
            {{ port }}
          </div>
        </v-list-item>
        <v-list-item v-if="imageConfig.Labels">
          <div style="max-width:20%">
            Labels
          </div>
          <div>
            <v-card variant="outlined" rounded="0">
              <v-table density="compact">
                <tbody>
                  <tr
                    v-for="(value, key, index) in imageConfig.Labels"
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
        <v-list-item v-if="imageConfig.Env">
          <div style="max-width:20%">
            ENV
          </div>
          <div>
            <v-card variant="outlined" rounded="0">
              <v-table>
                <tbody>
                  <tr
                    v-for="(key, index) in imageConfig.Env"
                    :key="index"
                  >
                    <td
                      style="width:100%;"
                      class="align-self-center text-truncate"
                    >
                      {{ key }}
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
        <v-card-title>Delete the image?</v-card-title>
        <v-card-text>
          Permanently delete {{ image.RepoTags?.[0] || image.Id }}?
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
  <v-alert v-else type="error">Image details are unavailable.</v-alert>
</template>

<script>
import { mapActions, mapGetters, mapState } from "vuex";

export default {
  data() {
    return { deleteDialog: false, deleting: false };
  },
  computed: {
    ...mapState("images", ["isLoading"]),
    ...mapGetters({
      getImageById: "images/getImageById"
    }),
    image() {
      const imageid = this.$route.params.imageid;
      return this.getImageById(imageid);
    },
    imageConfig() {
      return this.image?.Config || this.image?.ContainerConfig || {};
    }
  },
  methods: {
    ...mapActions({
      readImage: "images/readImage",
      updateImage: "images/updateImage",
      deleteImage: "images/deleteImage"
    }),
    formatBytes(bytes) {
      if (!Number.isFinite(bytes) || bytes < 0) return "-";
      if (bytes === 0) return "0 Bytes";
      const decimals = 2;
      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];

      const i = Math.floor(Math.log(bytes) / Math.log(k));

      return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    },
    getCMD(cmd) {
      return Array.isArray(cmd) ? cmd.join(" ") : cmd || null;
    },
    async confirmDelete() {
      if (this.deleting || !this.deleteDialog || !this.image) return;
      this.deleting = true;
      try {
        if (await this.deleteImage(this.image.Id)) {
          this.deleteDialog = false;
          await this.$router.push({ name: "Images" });
        }
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally {
        this.deleting = false;
      }
    }
  },
  created() {
    const imageid = this.$route.params.imageid;
    this.readImage(imageid);
  }
};
</script>

<style scoped></style>
