<template>
  <v-container fluid>
    <!-- Registry Tabs -->
    <v-tabs v-model="activeRegistryIndex" background-color="primary" dark>
      <v-tab key="dockerhub">Docker Hub</v-tab>
      <v-tab key="ghcr">GitHub (GHCR)</v-tab>
      <v-tab key="linuxserver">LinuxServer.io</v-tab>
    </v-tabs>

    <v-card flat class="pa-4">
      <v-row>
        <v-col cols="12">
          <v-text-field
            v-model="search"
            label="Search images..."
            prepend-inner-icon="mdi-magnify"
            clearable
            outlined
            dense
            @input="handleSearch"
          ></v-text-field>
        </v-col>
      </v-row>

      <v-row v-if="loading" justify="center">
        <v-progress-circular
          indeterminate
          color="primary"
        ></v-progress-circular>
      </v-row>

      <v-row v-else-if="images.length === 0" justify="center">
        <v-alert type="info">No images found.</v-alert>
      </v-row>

      <v-row v-else>
        <v-col
          v-for="image in images"
          :key="image.full_name"
          cols="12"
          md="6"
          lg="4"
        >
          <ImageCard
            :image="image"
            @click="showDetails(image)"
            @deploy="deploy(image)"
            @details="showDetails(image)"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Details Modal -->
    <v-dialog v-model="detailsDialog" max-width="600px">
      <v-card v-if="selectedImage">
        <v-card-title>
          <v-avatar size="32" class="mr-2" tile>
            <!-- Use cached logo logic? Or just replicate logic here? -->
            <!-- For simplicity and to fix the modal logo too, I'll use the util here or just reuse the logic inline since it is one image -->
            <img
              :src="modalLogoSrc"
              @error="handleModalLogoError"
              v-if="modalLogoSrc"
            />
            <v-icon v-else>mdi-docker</v-icon>
          </v-avatar>
          {{ selectedImage.full_name }}
          <v-spacer></v-spacer>
          <v-chip small color="primary" v-if="selectedImage.is_official"
            >Official</v-chip
          >
        </v-card-title>

        <v-card-text>
          <p class="body-1">{{ selectedImage.description }}</p>

          <v-row class="mb-2">
            <v-col cols="4">
              <v-icon>mdi-star</v-icon>
              {{ formatNumber(selectedImage.star_count) }} Stars
            </v-col>
            <v-col cols="4">
              <v-icon>mdi-download</v-icon>
              {{ formatNumber(selectedImage.pull_count) }} Pulls
            </v-col>
            <v-col cols="4" v-if="selectedImage.last_updated">
              <v-icon>mdi-calendar-clock</v-icon>
              {{ formatDate(selectedImage.last_updated) }}
            </v-col>
          </v-row>

          <v-divider class="mb-2"></v-divider>

          <div v-if="loadingTags" class="text-center">
            <v-progress-circular
              indeterminate
              small
              color="primary"
            ></v-progress-circular>
            Loading Tags...
          </div>
          <div v-else>
            <div class="subtitle-2 mb-1">Tags:</div>
            <v-chip-group column>
              <v-chip x-small v-for="tag in limitedTags" :key="tag">{{
                tag
              }}</v-chip>
              <v-chip x-small v-if="tags.length > 20"
                >+{{ tags.length - 20 }} more</v-chip
              >
            </v-chip-group>
          </div>
        </v-card-text>

        <v-card-actions>
          <v-btn text :href="getRegistryUrl(selectedImage)" target="_blank">
            View on Registry <v-icon x-small>mdi-open-in-new</v-icon>
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn text @click="detailsDialog = false">Close</v-btn>
          <v-btn color="primary" @click="deploy(selectedImage)"
            >Deploy Now</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
import axios from "axios";
import ImageCard from "./ImageCard.vue";
import { getImageLogoWithFallbacks } from "@/utils/imageLogos";

export default {
  name: "RegistryBrowser",
  components: {
    ImageCard
  },
  data() {
    return {
      activeRegistryIndex: 0,
      registries: ["dockerhub", "ghcr", "linuxserver"],
      search: "",
      images: [],
      loading: false,
      detailsDialog: false,
      selectedImage: null,
      tags: [],
      loadingTags: false,
      searchDebounce: null,
      // Modal logo logic
      modalLogoSrc: null,
      modalLogoSources: [],
      modalLogoIndex: 0
    };
  },
  computed: {
    activeRegistry() {
      return this.registries[this.activeRegistryIndex];
    },
    currentRegistryName() {
      return this.registries[this.activeRegistryIndex];
    },
    limitedTags() {
      return this.tags.slice(0, 20);
    }
  },
  watch: {
    activeRegistryIndex() {
      this.search = "";
      this.fetchImages();
    },
    selectedImage(newVal) {
      if (newVal) {
        this.initModalLogo(newVal);
      }
    }
  },
  methods: {
    initModalLogo(image) {
      const { sources, fallback } = getImageLogoWithFallbacks(
        image.full_name,
        image.source
      );
      this.modalLogoSources = [...sources];
      this.modalLogoIndex = 0;
      this.modalLogoSrc = this.modalLogoSources[0] || fallback;
    },
    handleModalLogoError() {
      this.modalLogoIndex++;
      if (this.modalLogoIndex < this.modalLogoSources.length) {
        this.modalLogoSrc = this.modalLogoSources[this.modalLogoIndex];
      } else {
        const { fallback } = getImageLogoWithFallbacks(
          this.selectedImage.full_name,
          this.selectedImage.source
        );
         if (this.modalLogoSrc === fallback) {
             return;
        }
        this.modalLogoSrc = fallback;
      }
    },
    formatNumber(num) {
      if (num === undefined || num === null) return "0";
      if (num >= 1000000000) return (num / 1000000000).toFixed(1) + "B";
      if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
      if (num >= 1000) return (num / 1000).toFixed(1) + "K";
      return num.toString();
    },
    formatDate(dateString) {
      if (!dateString) return "N/A";
      try {
        const date = new Date(dateString);
        return date.toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric"
        });
      } catch (e) {
        return dateString;
      }
    },
    async fetchImages() {
      this.loading = true;
      try {
        const registry = this.currentRegistryName;
        let url = "/api/registries/popular";
        let params = { registry: registry };

        if (this.search) {
          url = "/api/registries/search";
          params.query = this.search;
        }

        const response = await axios.get(url, { params });
        this.images = response.data;
      } catch (error) {
        console.error("Error fetching images:", error);
        if (this.$toast) this.$toast.error("Failed to fetch images");
      } finally {
        this.loading = false;
      }
    },
    handleSearch() {
      if (this.searchDebounce) clearTimeout(this.searchDebounce);
      this.searchDebounce = setTimeout(() => {
        this.fetchImages();
      }, 500);
    },
    async showDetails(image) {
      this.selectedImage = image;
      this.detailsDialog = true;
      this.tags = [];
      this.loadingTags = true;
      try {
        const registry = this.currentRegistryName;
        const response = await axios.get("/api/registries/tags", {
          params: {
            registry: registry,
            image: image.full_name
          }
        });
        this.tags = response.data;
      } catch (error) {
        console.error("Error fetching tags:", error);
        // Non-critical, just show empty
      } finally {
        this.loadingTags = false;
      }
    },
    deploy(image) {
      this.detailsDialog = false;
      this.$router.push({
        path: "/apps/deploy",
        query: { image: image.full_name }
      });
    },
    getRegistryUrl(image) {
      if (image.source === "dockerhub") {
        return `https://hub.docker.com/r/${image.full_name}`;
      } else if (image.source === "ghcr") {
        // ghcr.io/namespace/package
        const parts = image.full_name.replace("ghcr.io/", "").split("/");
        return `https://github.com/${parts[0]}?tab=packages`; // Best effort
      } else if (image.source === "linuxserver") {
        if (image.github_url) return image.github_url;
        return `https://docs.linuxserver.io/images/docker-${image.name}`;
      }
      return "#";
    }
  },
  mounted() {
    this.fetchImages();
  }
};
</script>

<style scoped>
.text-truncate-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
