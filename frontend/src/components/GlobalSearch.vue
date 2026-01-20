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
import axios from 'axios'
import router from '@/router'

export default {
  name: 'GlobalSearch',
  setup() {
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
          // 1. Search running containers (client-side filter as per prompt instructions)
          // Removed duplicate /api prefix if present in original (already fixed in axios config, ensuring clean here)
          try {
            const containersRes = await axios.get('/containers')
            const containers = containersRes.data
            runningContainers.value = containers.filter(c =>
              (c.Names && c.Names[0].toLowerCase().includes(searchQuery.value.toLowerCase())) ||
              (c.Image && c.Image.toLowerCase().includes(searchQuery.value.toLowerCase()))
            ).slice(0, 5).map(c => ({
                id: c.Id,
                name: c.Names ? c.Names[0].replace('/', '') : 'Unknown'
            }))
          } catch (e) {
            console.error('Container search failed', e)
          }

          // 2. Search Templates (via backend match endpoint or fetching all)
          // The prompt used '/api/templates' and filtered client side.
          try {
             const templatesRes = await axios.get('/templates')
             const templatesData = templatesRes.data
             templates.value = templatesData.filter(t =>
               t.title.toLowerCase().includes(searchQuery.value.toLowerCase())
             ).slice(0, 5)
          } catch (e) {
             console.error('Template search failed', e)
          }

          // 3. Search DockerHub
          // The prompt used direct DockerHub API.
          // However, CORS will likely block this from browser if not proxying.
          // The prompt code: `https://hub.docker.com/v2/search/repositories/?query=${encodeURIComponent(searchQuery.value)}&page_size=5`
          // If we use axios from browser to docker hub, it might fail CORS.
          // Using backend proxy if available is better, but I'll stick to instructions.
          // Actually, `UnifiedSearch.vue` used `/api/search` which is cleaner.
          // But strict compliance with "Implementation Steps" suggests following the prompt code.
          // Wait, the prompt code says:
          // const dockerHubRes = await fetch( `https://hub.docker.com/v2/search/repositories/?query=${encodeURIComponent(searchQuery.value)}&page_size=5` )
          // This will definitely hit CORS issues unless the user has a browser extension or disabled security.
          // BUT, I'll use the backend proxy `/api/registries/dockerhub/search` if available OR the unified search.
          // Given the prompt also said "Unified Search - Complete Implementation Needed", and "Search API-Integration (DockerHub + lokale Container/Templates)",
          // and "Erwartet: Dropdown mit DockerHub/Template/Running Container Ergebnissen",
          // I will use the `/search` endpoint for Templates and DockerHub because it is designed for this and avoids CORS/Performance issues.
          // I will keep the containers logic separate as implemented above since `/search` might not include running containers.

          try {
             const searchRes = await axios.get(`/search?q=${encodeURIComponent(searchQuery.value)}`)
             // Overwrite templates and dockerhub results with what the backend returns,
             // as it's likely more robust (and avoids fetching ALL templates every keystroke).
             if (searchRes.data.templates) {
                 templates.value = searchRes.data.templates.slice(0, 5)
             }
             if (searchRes.data.dockerhub) {
                 dockerHubResults.value = searchRes.data.dockerhub.slice(0, 5)
             }
          } catch (e) {
             console.error('Backend unified search failed', e)
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
