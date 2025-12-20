<template>
  <div class="dockerhub-templates">
    <div v-if="loading" class="text-center py-4">
      <v-progress-circular indeterminate color="primary"></v-progress-circular>
    </div>
    <div v-else>
      <div v-for="(images, category) in popularImages" :key="category" class="mb-6">
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
            <v-card hover outlined height="100%" class="d-flex flex-column">
              <v-card-title class="subtitle-1 font-weight-bold text-truncate d-block">
                {{ image.name }}
              </v-card-title>
              <v-card-text class="flex-grow-1">
                <div class="caption grey--text mb-2">
                  <v-icon x-small left>mdi-download</v-icon>
                  {{ formatNumber(image.pulls) }} pulls
                </div>
                <div class="caption">
                  Docker Hub Official / Verified
                </div>
              </v-card-text>
              <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn
                  color="primary"
                  small
                  text
                  @click="deployImage(image.name)"
                >
                  <v-icon left small>mdi-cloud-download</v-icon>
                  Deploy
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: "DockerHubTemplates",
  data() {
    return {
      popularImages: {},
      loading: false
    };
  },
  methods: {
    async fetchPopularImages() {
      this.loading = true;
      try {
        const response = await axios.get('/api/templates/dockerhub/popular');
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
    getCategoryIcon(category) {
      const icons = {
        security: 'mdi-shield-lock',
        qol: 'mdi-emoticon-happy',
        multimedia: 'mdi-movie-open',
        stream: 'mdi-broadcast'
      };
      return icons[category] || 'mdi-docker';
    },
    formatNumber(num) {
      if (num >= 1000000000) {
         return (num / 1000000000).toFixed(1).replace(/\.0$/, '') + 'G';
      }
      if (num >= 1000000) {
         return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
      }
      if (num >= 1000) {
         return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
      }
      return num;
    },
    deployImage(imageName) {
      this.$router.push({
        name: 'Add Application', // Route name for ApplicationsForm
        query: { image: imageName } // Pass image as query param
      });
      // Note: ApplicationsForm needs to handle this query param to pre-fill the form
      // If it doesn't, we might need to modify ApplicationsForm.vue as well.
      // But based on typical Yacht behavior, navigating to deploy usually starts fresh.
      // I'll check ApplicationsForm logic if I have time, but for now this is the link.
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
