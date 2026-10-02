<template lang="html">
  <div class="images-list component" style="width: 100%">
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
        Images
        <v-dialog v-model="pullDialog" max-width="290">
          <template v-slot:activator="{ props }">
            <v-btn class="ml-2" color="secondary" v-bind="props" aria-label="Pull image" title="Pull image">
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
                  aria-label="Prune unused images"
                  @click="pruneDialog = true"
                >
                  <v-icon>mdi-broom</v-icon>
                </v-btn>
              </template>
              <span>Prune Unused Images</span>
            </v-tooltip>
          </template>
          <v-card color="foreground">
            <v-card-title class="headline" style="word-break: break-all;">
              Pull Image
            </v-card-title>
            <v-card-text>
              Pull an image.
            </v-card-text>
            <form ref="form" @submit.prevent="submit">
              <v-text-field
                label="Image"
                class="mx-5"
                placeholder="nginx:latest"
                required
                v-model="form.image"
              >
              </v-text-field>
            </form>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="pullDialog = false">
                Cancel
              </v-btn>
              <v-btn
                variant="text"
                color="primary"
                :loading="pulling"
                :disabled="pulling || !form.image.trim()"
                @click="submit"
              >
                Pull
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
        class="mx-auto image-datatable foreground"
        :headers="headers"
        :items="images"
        :loading="isLoading"
        loading-text="Loading images..."
        :items-per-page="25"
        :items-per-page-options="[15, 25, 50, -1]"
        :search="search"
        @click:row="handleRowClick"
      >
        <template #no-data>
          <div>
            No Images available.
          </div>
        </template>
        <template v-slot:item.RepoTags="{ item }">
          <div class="d-flex">
            <span class="align-streatch text-truncate nametext mt-2">{{
              item.RepoTags?.[0] || handleDigests(item)
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
                  :aria-label="`Actions for ${item.Id}`"
                >
                  <v-icon>mdi-dots-horizontal</v-icon>
                </v-btn>
              </template>
              <v-list color="foreground" density="compact">
                <v-list-item @click="imageDetails(item.Id)">
                  <span>
                    <v-icon>mdi-eye</v-icon>
                  </span>
                  <v-list-item-title>View</v-list-item-title>
                </v-list-item>
                <v-list-item
                  v-if="item.RepoTags?.[0]"
                  @click="updateImage(item.Id)"
                >
                  <span>
                    <v-icon>mdi-update</v-icon>
                  </span>
                  <v-list-item-title>Pull</v-list-item-title>
                </v-list-item>
                <v-divider />
                <v-list-item
                  @click="
                    selectedImage = item;
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
        <template v-slot:item.Id="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.Id }}
            </span>
          </div>
        </template>
        <template v-slot:item.Created="{ item }">
          <span
            class="d-inline-block text-truncate flex-grow-1 flex-shrink-0"
            >{{ $formatDate(new Date(item.Created * 1000)) }}</span
          >
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="pruneDialog" max-width="420" :persistent="pruning">
      <v-card>
        <v-card-title>Prune unused images?</v-card-title>
        <v-card-text>Remove unused images on this Docker host. Images required later may need to be downloaded again.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="pruning" @click="pruneDialog = false">Cancel</v-btn>
          <v-btn color="warning" :loading="pruning" :disabled="pruning" @click="pruneImages">Prune</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-if="selectedImage" v-model="deleteDialog" max-width="290">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Delete the image?
        </v-card-title>
        <v-card-text>
          Are you sure you want to permanently delete the image?<br />
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
      selectedImage: null,
      deleteDialog: false,
      deleting: false,
      form: {
        image: ""
      },
      pullDialog: false,
      pulling: false,
      pruneDialog: false,
      pruning: false,
      search: "",
      headers: [
        {
          title: "Tag",
          key: "RepoTags",
          sortable: true
        },
        {
          title: "ID",
          key: "Id",
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
        if (await this.deleteImage(this.selectedImage.Id)) this.deleteDialog = false;
      } finally {
        this.deleting = false;
      }
    },
    ...mapActions({
      readImages: "images/readImages",
      updateImage: "images/updateImage",
      deleteImage: "images/deleteImage",
      writeImage: "images/writeImage"
    }),
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/resources/images/${item.Id}` });
    },
    imageDetails(imageid) {
      this.$router.push({ path: `/resources/images/${imageid}` });
    },
    async submit() {
      if (this.pulling || !this.form.image.trim()) return;
      this.pulling = true;
      try {
        if (await this.writeImage({ image: this.form.image.trim() })) {
          this.pullDialog = false;
          this.form.image = '';
        }
      } finally {
        this.pulling = false;
      }
    },
    handleDigests(item) {
      return item.RepoDigests?.[0]?.split('@')[0] || item.Id?.replace(/^sha256:/, '').slice(0, 10) || 'Untagged image';
    },
    async pruneImages() {
      if (this.pruning) return;
      this.pruning = true;
      try {
        const { data } = await axios.post('/settings/prune/images');
        const deleted = new Set((data?.ImagesDeleted || []).map(item => item.Deleted).filter(Boolean)).size;
        this.$store.commit('snackbar/setMessage', `${deleted} images pruned. Space reclaimed: ${data?.SpaceReclaimed || 0} bytes.`);
        this.pruneDialog = false;
        await this.readImages();
      } catch (error) {
        this.$store.commit('snackbar/setErr', error);
      } finally {
        this.pruning = false;
      }
    }
  },
  computed: {
    ...mapState("images", ["images", "isLoading"])
  },
  mounted() {
    this.readImages();
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
.image-datatable {
  overflow-x: auto;
}
</style>
