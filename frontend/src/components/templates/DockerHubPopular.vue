<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12">
        <v-text-field
          v-model="search"
          label="Search images..."
          prepend-inner-icon="mdi-magnify"
          clearable outlined dense
        />
      </v-col>
    </v-row>

    <!-- Removed v-tabs and category handling -->

    <v-row class="mt-4">
      <v-col v-for="image in filteredImages" :key="image.full_name"
             cols="12" md="6" lg="4">
        <v-card hover @click="selectImage(image)">
          <v-card-title>
            {{ image.full_name }}
            <v-spacer />
            <v-chip small color="primary" v-if="image.is_official">Official</v-chip>
          </v-card-title>
          <v-card-subtitle>{{ image.description }}</v-card-subtitle>
          <v-card-text>
            <v-row dense>
              <v-col cols="6">
                <v-icon small>mdi-download</v-icon>
                {{ formatNumber(image.pull_count) }} pulls
              </v-col>
              <v-col cols="6">
                <v-icon small>mdi-star</v-icon>
                {{ formatNumber(image.star_count) }} stars
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-btn text color="primary">Deploy</v-btn>
            <v-btn text>Details</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <v-row v-if="loading" justify="center" class="mt-4">
      <v-progress-circular indeterminate color="primary" />
    </v-row>
    <v-row v-else-if="!loading && filteredImages.length === 0" justify="center" class="mt-4">
      <v-alert type="info">No images found.</v-alert>
    </v-row>
  </v-container>
</template>

<script>
import axios from 'axios';

export default {
  name: 'DockerHubPopular',
  data() {
    return {
      search: '',
      imagesData: [], // Changed to array
      loading: false,
    };
  },
  computed: {
    filteredImages() {
      // imagesData is now a flat array
      if (!this.search) return this.imagesData;
      const searchLower = this.search.toLowerCase();
      return this.imagesData.filter(img =>
        img.full_name.toLowerCase().includes(searchLower) ||
        img.description.toLowerCase().includes(searchLower)
      );
    },
  },
  methods: {
    async fetchPopularImages() {
      this.loading = true;
      try {
        const response = await axios.get('/api/dockerhub/popular');
        // Flatten the response object values into a single array
        const data = response.data;
        let allImages = [];
        if (typeof data === 'object' && !Array.isArray(data)) {
            Object.values(data).forEach(categoryImages => {
                if (Array.isArray(categoryImages)) {
                    allImages = allImages.concat(categoryImages);
                }
            });
        } else if (Array.isArray(data)) {
            allImages = data;
        }
        this.imagesData = allImages;
      } catch (error) {
        console.error('Error:', error);
        if (this.$toast) {
             this.$toast.error('Failed to load images');
        }
      } finally {
        this.loading = false;
      }
    },
    formatNumber(num) {
      if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
      if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
      return num;
    },
    selectImage(image) {
      this.$router.push({
        path: '/apps/deploy',
        query: { image: image.full_name }
      });
    },
  },
  mounted() {
    this.fetchPopularImages();
  },
};
</script>
