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

    <v-tabs v-model="activeCategory" color="primary">
      <v-tab v-for="category in categories" :key="category">
        {{ category }}
      </v-tab>
    </v-tabs>

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
  </v-container>
</template>

<script>
import axios from 'axios';

export default {
  name: 'DockerHubPopular',
  data() {
    return {
      search: '',
      activeCategory: 0,
      categories: ['Security', 'QoL', 'Multimedia', 'Stream'],
      imagesData: {},
      loading: false,
    };
  },
  computed: {
    currentCategory() {
      return this.categories[this.activeCategory];
    },
    filteredImages() {
      const categoryImages = this.imagesData[this.currentCategory] || [];
      if (!this.search) return categoryImages;
      const searchLower = this.search.toLowerCase();
      return categoryImages.filter(img =>
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
        this.imagesData = response.data;
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
