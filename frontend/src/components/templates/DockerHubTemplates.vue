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
          <v-icon left color="primary">{{ getCategoryIcon(category) }}</v-icon>
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

// Sub-component for Image Card to reduce code duplication
const ImageCard = {
  props: ["image"],
  template: `
    <v-card hover outlined height="100%" class="d-flex flex-column">
      <v-card-title class="subtitle-1 font-weight-bold text-truncate d-block pb-1">
        {{ image.name }}
      </v-card-title>
      <v-card-subtitle class="caption py-1">
         <v-chip v-if="image.is_official" x-small color="success" class="mr-1" label>OFFICIAL</v-chip>
         <span v-else class="grey--text">Community</span>
      </v-card-subtitle>
      <v-card-text class="flex-grow-1 py-1">
        <div class="d-flex align-center mb-2">
           <v-icon x-small class="mr-1">mdi-download</v-icon>
           <span class="caption font-weight-bold mr-3">{{ formatNumber(image.pulls) }}</span>

           <v-icon x-small class="mr-1">mdi-star</v-icon>
           <span class="caption font-weight-bold">{{ formatNumber(image.stars) }}</span>
        </div>
        <div class="caption grey--text text--lighten-1" style="line-height: 1.2; max-height: 60px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;">
           {{ image.description || 'No description available.' }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="primary"
          small
          depressed
          @click="$emit('deploy', image.name)"
        >
          <v-icon left small>mdi-cloud-download</v-icon>
          Deploy
        </v-btn>
      </v-card-actions>
    </v-card>
  `,
  methods: {
    formatNumber(num) {
      if (!num) return "0";
      if (num >= 1000000000) {
        return (num / 1000000000).toFixed(1).replace(/\.0$/, "") + "G";
      }
      if (num >= 1000000) {
        return (num / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
      }
      if (num >= 1000) {
        return (num / 1000).toFixed(1).replace(/\.0$/, "") + "k";
      }
      return num.toString();
    }
  }
};

export default {
  name: "DockerHubTemplates",
  components: {
    ImageCard
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
      try {
        const response = await axios.get("/templates/dockerhub/popular");
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

      if (!val || val.length < 2) {
        this.searchResults = [];
        return;
      }

      this.debounceTimer = setTimeout(() => {
        this.searchDockerHub(val);
      }, 500); // 500ms debounce
    },
    async searchDockerHub(query) {
      this.loading = true;
      try {
        const response = await axios.get(
          `/api/templates/dockerhub/search?query=${encodeURIComponent(query)}`
        );
        this.searchResults = response.data.results;
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
