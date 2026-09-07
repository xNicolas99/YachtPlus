<template>
  <div class="dockerhub-templates">
    <!-- Search Bar -->
    <v-row class="mb-4">
      <v-col cols="12">
        <v-text-field
          v-model="searchQuery"
          @input="handleSearchInput"
          label="Search Docker Hub"
          placeholder="nginx, plex, etc."
          prepend-inner-icon="mdi-magnify"
          clearable
          outlined
          dense
          hide-details
          class="mb-2"
        ></v-text-field>
      </v-col>
    </v-row>

    <!-- Loading State -->
    <div v-if="loading" class="text-center py-5">
      <v-progress-circular
        indeterminate
        color="primary"
        size="64"
      ></v-progress-circular>
      <div class="mt-3 caption grey--text">
        Fetching data from Docker Hub...
      </div>
    </div>

    <!-- Search Results -->
    <div v-else-if="searchQuery && searchQuery.length >= 2">
      <h3 class="mb-4 primary--text font-weight-bold">
        Search Results for "{{ searchQuery }}"
      </h3>

      <div
        v-if="searchResults.length === 0"
        class="text-center py-5 grey--text"
      >
        No results found.
      </div>

      <v-row>
        <v-col
          v-for="(image, index) in searchResults"
          :key="index"
          cols="12"
          sm="6"
          md="4"
          lg="3"
        >
          <image-card :image="image" @deploy="deployImage" />
        </v-col>
      </v-row>
    </div>

    <!-- Popular Images (Default View) -->
    <div v-else>
      <div
        v-for="(images, category) in popularImages"
        :key="category"
        class="mb-6"
      >
        <h3 class="text-capitalize mb-2 primary--text font-weight-bold">
          <v-icon start color="primary">{{ getCategoryIcon(category) }}</v-icon>
          {{ category }}
        </h3>
        <v-row>
          <v-col
            v-for="(image, index) in images"
            :key="index"
            cols="12"
            sm="6"
            md="4"
            lg="3"
          >
            <image-card :image="image" @deploy="deployImage" />
          </v-col>
        </v-row>
      </div>
    </div>
  </div>
</template>

<script>
import axios from "axios";

import DockerHubImageCard from "./DockerHubImageCard.vue";

export default {
  name: "DockerHubTemplates",
  components: {
    DockerHubImageCard
  },
  data() {
    return {
      popularImages: {},
      searchResults: [],
      searchQuery: "",
      loading: false,
      debounceTimer: null
    };
  },
  methods: {
    async fetchPopularImages() {
      this.loading = true;
      this.popularImages = {}; // Clear immediately to fix Bug #4
      try {
        // Changed from /templates/dockerhub/popular to /registries/popular
        // Verified: This endpoint now points to the new Registries Router.
        const response = await axios.get("/registries/popular");
        this.popularImages = response.data;
      } catch (error) {
        console.error("Failed to fetch popular images:", error);
        if (this.$toast) {
          this.$toast.error("Failed to load popular Docker Hub images.");
        }
      } finally {
        this.loading = false;
      }
    },
    handleSearchInput(val) {
      if (this.debounceTimer) clearTimeout(this.debounceTimer);

      // Clear search results immediately to fix Bug #4
      this.searchResults = [];

      if (!val || val.length < 2) {
        return;
      }

      this.debounceTimer = setTimeout(() => {
        this.searchDockerHub(val);
      }, 500); // 500ms debounce
    },
    async searchDockerHub(query) {
      this.loading = true;
      this.searchResults = []; // Clear immediately to fix Bug #4
      try {
        // Changed from /templates/dockerhub/search to /registries/search
        // Verified: This endpoint now points to the new Registries Router.
        const response = await axios.get(
          `/registries/search?query=${encodeURIComponent(query)}`
        );
        this.searchResults = response.data;  // F27: backend returns a bare array
      } catch (error) {
        console.error("Search failed:", error);
        if (this.$toast) {
          this.$toast.error("Docker Hub search failed.");
        }
      } finally {
        this.loading = false;
      }
    },
    getCategoryIcon(category) {
      const icons = {
        security: "mdi-shield-lock",
        qol: "mdi-emoticon-happy",
        multimedia: "mdi-movie-open",
        stream: "mdi-broadcast"
      };
      return icons[category] || "mdi-docker";
    },
    deployImage(imageName) {
      this.$router.push({
        path: "/apps/deploy",
        query: { image: imageName }
      });
    }
  },
  mounted() {
    this.fetchPopularImages();
  }
};
</script>

<style scoped>
.text-capitalize {
  text-transform: capitalize;
}
</style>
