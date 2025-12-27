<template>
  <v-container fluid>
    <!-- Registry Tabs -->
    <v-tabs v-model="activeRegistryIndex" background-color="primary" dark>
      <v-tab key="all">All Registries</v-tab>
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
            @keydown.enter="fetchImages"
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
          :key="image.full_name + image.source"
          cols="12"
          md="6"
          lg="4"
        >
          <!-- Wrapper to inject badge/source if needed -->
          <div style="position: relative">
            <ImageCard
              :image="image"
              @click="showDetails(image)"
              @deploy="deploy(image)"
              @details="showDetails(image)"
            />
            <!-- Badge Overlay -->
            <v-chip
              small
              :color="getBadgeColor(image.source)"
              text-color="white"
              style="position: absolute; top: 10px; right: 10px; z-index: 2"
            >
              <v-icon left x-small>{{ getBadgeIcon(image.source) }}</v-icon>
              {{ getBadgeText(image.source) }}
            </v-chip>
          </div>
        </v-col>
      </v-row>
    </v-card>

    <!-- Details Modal -->
    <v-dialog v-model="detailsDialog" max-width="600px">
      <v-card v-if="selectedImage">
        <v-card-title>
          <v-avatar size="32" class="mr-2" tile>
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
      registries: ["all", "dockerhub", "ghcr", "linuxserver"],
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
    currentRegistryName() {
      return this.registries[this.activeRegistryIndex];
    },
    limitedTags() {
      return this.tags.slice(0, 20);
    }
  },
  watch: {
    activeRegistryIndex() {
      // Clear images immediately to fix Bug #4
      this.images = [];
      // Do not clear search if switching tabs to allow searching same query on other registries?
      // User request said: "Beim Wechsel zwischen Tabs werden alte Ergebnisse geleert"
      // But for Unified Search, it might be nice to keep the query.
      // I'll keep the search query but trigger a new fetch.
      // If the user meant "clear everything", I should clear search too.
      // But usually retaining search query is better UX.
      // I will re-fetch.
      this.fetchImages();
    },
    selectedImage(newVal) {
      if (newVal) {
        this.initModalLogo(newVal);
      }
    }
  },
  methods: {
    getBadgeColor(source) {
      switch (source) {
        case "dockerhub":
          return "blue darken-2";
        case "ghcr":
          return "green darken-2";
        case "linuxserver":
          return "orange darken-2";
        default:
          return "grey";
      }
    },
    getBadgeIcon(source) {
      switch (source) {
        case "dockerhub":
          return "mdi-docker";
        case "ghcr":
          return "mdi-package-variant";
        case "linuxserver":
          return "mdi-linux";
        default:
          return "mdi-help-circle";
      }
    },
    getBadgeText(source) {
      switch (source) {
        case "dockerhub":
          return "Docker Hub";
        case "ghcr":
          return "GHCR";
        case "linuxserver":
          return "LinuxServer";
        default:
          return source;
      }
    },
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
    async fetchRegistryImages(registry, query) {
      try {
        let url = "/registries/popular";
        let params = { registry: registry };
        if (query) {
          url = "/registries/search";
          params.query = query;
        }
        const response = await axios.get(url, { params });
        return response.data;
      } catch (error) {
        console.error(`Error fetching ${registry}:`, error);
        return [];
      }
    },
    async fetchImages() {
      this.loading = true;
      this.images = []; // Clear immediately
      try {
        const registry = this.currentRegistryName;

        if (registry === "all") {
          // Unified Search
          const queries = ["dockerhub", "ghcr", "linuxserver"];
          const results = await Promise.all(
            queries.map(r => this.fetchRegistryImages(r, this.search))
          );

          let allImages = [];
          results.forEach(res => {
              if(Array.isArray(res)) allImages = allImages.concat(res);
          });

          // Sort by pull count (descending)
          allImages.sort((a, b) => (b.pull_count || 0) - (a.pull_count || 0));
          this.images = allImages;

        } else {
          // Single Registry Search
          this.images = await this.fetchRegistryImages(registry, this.search);
        }
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
        // Use the source of the image for fetching tags
        const registry = image.source || this.currentRegistryName;
        // If 'all', we must rely on image.source which should be present
        if(registry === 'all') {
            console.error("Image source missing for tag fetch");
            this.loadingTags = false;
            return;
        }

        const response = await axios.get("/registries/tags", {
          params: {
            registry: registry,
            image: image.full_name
          }
        });
        this.tags = response.data;
      } catch (error) {
        console.error("Error fetching tags:", error);
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
        const parts = image.full_name.replace("ghcr.io/", "").split("/");
        return `https://github.com/${parts[0]}?tab=packages`;
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
