<template>
  <div class="search-container">
    <input
      v-model="searchQuery"
      @input="handleSearch"
      @focus="showDropdown = true"
      placeholder="Search (Apps, Templates, DockerHub)"
      class="search-input"
    />

    <div v-if="showDropdown && searchQuery.length > 0" class="search-dropdown">
      <!-- Running Containers -->
      <div v-if="runningContainers.length > 0" class="search-section">
        <div class="section-header">Running Containers</div>
        <div
          v-for="container in runningContainers"
          :key="container.id"
          @click="navigateTo(`/apps/${container.name}/info`)"
          class="search-item"
        >
          <span class="item-icon">🟢</span>
          <span>{{ container.name }}</span>
        </div>
      </div>

      <!-- Templates -->
      <div v-if="templates.length > 0" class="search-section">
        <div class="section-header">Templates</div>
        <div
          v-for="template in templates"
          :key="template.id"
          @click="deployTemplate(template.id)"
          class="search-item"
        >
          <span class="item-icon">📋</span>
          <span>{{ template.title }}</span>
        </div>
      </div>

      <!-- DockerHub Results -->
      <div v-if="dockerHubResults.length > 0" class="search-section">
        <div class="section-header">DockerHub</div>
        <div
          v-for="image in dockerHubResults"
          :key="image.name"
          @click="deployImage(image.name)"
          class="search-item"
        >
          <span class="item-icon">🐳</span>
          <span>{{ image.name }}</span>
          <span class="item-meta">⭐ {{ image.star_count || image.stars }}</span>
        </div>
      </div>

      <div v-if="isLoading" class="search-loading">Searching...</div>
      <div v-if="!isLoading && totalResults === 0" class="no-results">
        No results found
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useStore } from 'vuex'
import axios from 'axios'
import router from '@/router'

export default {
  name: 'GlobalSearch',
  setup() {
    const store = useStore()
    const searchQuery = ref('')
    const showDropdown = ref(false)
    const isLoading = ref(false)
    const runningContainers = ref([])
    const templates = ref([])
    const dockerHubResults = ref([])
    let searchTimeout = null

    const totalResults = computed(() =>
      runningContainers.value.length + templates.value.length + dockerHubResults.value.length
    )

    const handleSearch = async () => {
      if (searchQuery.value.length < 2) {
        runningContainers.value = []
        templates.value = []
        dockerHubResults.value = []
        return
      }

      if (searchTimeout) clearTimeout(searchTimeout)

      searchTimeout = setTimeout(async () => {
        isLoading.value = true
        try {
          // Fetch unified search from backend
          const searchPromise = axios.get(`/search?q=${encodeURIComponent(searchQuery.value)}`).catch(e => {
            console.error('Backend unified search failed', e)
            return { data: {} }
          })

          // Search local containers from Vuex store
          const query = searchQuery.value.toLowerCase()
          const containers = store.state.apps.apps || []
          runningContainers.value = containers.filter(c =>
            (c.name && c.name.toLowerCase().includes(query)) ||
            (c.Config && c.Config.Image && c.Config.Image.toLowerCase().includes(query))
          ).slice(0, 5).map(c => ({
              id: c.short_id || c.name,
              name: c.name
          }))

          const searchRes = await searchPromise

          // 2. Process Templates & DockerHub from unified search
          if (searchRes.data.templates) {
              templates.value = searchRes.data.templates.slice(0, 5)
          } else {
              templates.value = []
          }

          if (searchRes.data.dockerhub) {
              dockerHubResults.value = searchRes.data.dockerhub.slice(0, 5)
          } else {
              dockerHubResults.value = []
          }

        } catch (error) {
          console.error('Search error:', error)
        } finally {
          isLoading.value = false
        }
      }, 300)
    }

    const navigateTo = (path) => {
      router.push({ path }).catch(() => {})
      showDropdown.value = false
      searchQuery.value = ''
    }

    const deployTemplate = (templateId) => {
        // Route name 'Deploy' exists in router/index.js:
        // path: "deploy/:appId", name: "Deploy"
        router.push({ name: 'Deploy', params: { appId: templateId } }).catch(() => {})
        showDropdown.value = false
        searchQuery.value = ''
    }

    const deployImage = (imageName) => {
      // Navigate to ApplicationsForm with image query
      // In router: path: "deploy", name: "Add Application"
      // or path: "deploy/:appId", name: "Deploy"
      // The prompt code used: router.push(`/apps/deploy?image=${encodeURIComponent(imageName)}`)
      // This matches path "/apps/deploy".
      router.push({ path: '/apps/deploy', query: { image: imageName } }).catch(() => {})
      showDropdown.value = false
      searchQuery.value = ''
    }

    const handleClickOutside = (e) => {
        const el = document.querySelector('.search-container')
        if (el && !el.contains(e.target)) {
            showDropdown.value = false
        }
    }

    const handleEsc = (e) => {
        if (e.key === 'Escape') {
            showDropdown.value = false
        }
    }

    onMounted(() => {
        document.addEventListener('click', handleClickOutside)
        document.addEventListener('keydown', handleEsc)
    })

    onBeforeUnmount(() => {
        document.removeEventListener('click', handleClickOutside)
        document.removeEventListener('keydown', handleEsc)
    })

    return {
      searchQuery,
      showDropdown,
      isLoading,
      runningContainers,
      templates,
      dockerHubResults,
      totalResults,
      handleSearch,
      navigateTo,
      deployTemplate,
      deployImage
    }
  }
}
</script>

<style scoped>
/* Search Input Styling */
.search-input {
  width: 100%;
  padding: 8px 16px;
  background-color: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: #fff;
  outline: none;
  transition: all 0.3s;
}

.search-input:focus {
  background-color: rgba(0, 0, 0, 0.3);
  border-color: #64b5f6;
}

.search-container {
  position: relative;
  width: 500px; /* Adjust width as needed */
  z-index: 100;
}

.search-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: #1a1d2e;
  border: 1px solid #2d3548;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  max-height: 500px;
  overflow-y: auto;
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.search-section {
  padding: 8px 0;
  border-bottom: 1px solid #2d3548;
}

.search-section:last-child {
  border-bottom: none;
}

.section-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #64b5f6;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.search-item {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.search-item:hover {
  background: #2d3548;
  padding-left: 20px;
}

.item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.item-meta {
  margin-left: auto;
  font-size: 12px;
  color: #9e9e9e;
}

.search-loading,
.no-results {
  padding: 24px;
  text-align: center;
  color: #9e9e9e;
  font-size: 14px;
}
</style>
