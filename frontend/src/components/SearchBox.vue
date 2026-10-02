<template>
  <div ref="root" class="search-container" @focusout="handleFocusOut">
    <div class="search-field">
      <input
        ref="input"
        :value="query"
        :aria-label="label"
        :aria-controls="`${searchId}-results`"
        :aria-describedby="`${searchId}-status`"
        :aria-expanded="isOpen"
        :aria-activedescendant="activeIndex >= 0 && isOpen ? `${searchId}-option-${activeIndex}` : undefined"
        role="combobox"
        aria-autocomplete="list"
        autocomplete="off"
        maxlength="128"
        placeholder="Search Apps, Templates, DockerHub"
        class="search-input"
        @input="updateQuery($event.target.value)"
        @focus="isOpen = true"
        @keydown="handleKeydown"
      />
      <button v-if="query" type="button" class="search-clear" aria-label="Clear search" @click="clearSearch">×</button>
    </div>
    <div v-show="isOpen" class="search-dropdown">
      <div :id="`${searchId}-results`" role="listbox" :aria-label="label" :aria-busy="isLoading">
        <div v-for="group in groups" :key="group.name" role="group" :aria-label="group.name">
          <div class="section-header" aria-hidden="true">{{ group.name }}</div>
          <button
            v-for="entry in group.items"
            :id="`${searchId}-option-${entry.index}`"
            :key="entry.item.key"
            type="button"
            role="option"
            tabindex="-1"
            :aria-selected="activeIndex === entry.index"
            class="search-item"
            :class="{ 'search-item-active': activeIndex === entry.index }"
            @mousedown.prevent
            @mouseenter="activeIndex = entry.index"
            @click="selectResult(entry.item)"
          >
            <span class="item-title">{{ entry.item.title }}</span>
            <span v-if="entry.item.description" class="item-description">{{ entry.item.description }}</span>
          </button>
        </div>
      </div>
      <div :id="`${searchId}-status`" role="status" aria-live="polite" class="search-status">
        <template v-if="error">{{ error }}</template>
        <template v-else-if="isLoading">Searching…</template>
        <template v-else-if="query.trim().length < 2">Type at least 2 characters to search.</template>
        <template v-else-if="!items.length">No results found.</template>
        <template v-else>{{ items.length }} results. Use the arrow keys and Enter to select.</template>
      </div>
      <button v-if="error" type="button" class="search-retry" @mousedown.prevent @click="retrySearch">Retry search</button>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import { isNavigationFailure } from 'vue-router';
import { localSearchResults, remoteSearchResults, searchDestination, SEARCH_DELAY_MS, SEARCH_TIMEOUT_MS } from '@/utils/search';

export default {
  name: 'SearchBox',
  props: {
    label: { type: String, default: 'Search Apps, Templates and DockerHub' },
    autofocus: { type: Boolean, default: false },
  },
  emits: ['input', 'selected'],
  data: () => ({
    query: '', items: [], isOpen: false, isLoading: false, error: '', activeIndex: -1,
    requestId: 0, selectionRequestId: null, debounceTimer: null, requestTimer: null, requestController: null,
  }),
  computed: {
    searchId() { return `yacht-search-${this.$.uid}`; },
    groups() {
      return ['Apps', 'Templates', 'DockerHub'].map(name => ({
        name, items: this.items.map((item, index) => ({ item, index })).filter(entry => entry.item.source === name),
      })).filter(group => group.items.length);
    },
  },
  mounted() {
    document.addEventListener('pointerdown', this.handleOutside);
    if (this.autofocus) this.$nextTick(() => this.$refs.input.focus());
  },
  beforeUnmount() {
    this.cancelSearch();
    document.removeEventListener('pointerdown', this.handleOutside);
  },
  methods: {
    cancelSearch() {
      ++this.requestId;
      clearTimeout(this.debounceTimer);
      clearTimeout(this.requestTimer);
      this.debounceTimer = this.requestTimer = null;
      this.requestController?.abort();
      this.requestController = null;
    },
    updateQuery(value) {
      this.query = value;
      this.$emit('input', value);
      this.scheduleSearch();
    },
    scheduleSearch(immediate = false) {
      this.cancelSearch();
      this.activeIndex = -1;
      this.error = '';
      this.isOpen = true;
      const query = this.query.trim();
      this.items = localSearchResults(this.$store.state.apps?.apps, query);
      this.isLoading = query.length >= 2;
      if (!this.isLoading) return;
      const requestId = this.requestId;
      if (immediate) return this.fetchResults(query, requestId);
      this.debounceTimer = setTimeout(() => {
        this.debounceTimer = null;
        this.fetchResults(query, requestId);
      }, SEARCH_DELAY_MS);
    },
    async fetchResults(query, requestId) {
      const controller = new AbortController();
      this.requestController = controller;
      let timeout;
      let handleAbort;
      try {
        // Settle cancellation even if a transport ignores AbortSignal.
        const cancelled = new Promise((_, reject) => {
          handleAbort = () => {
            const error = new Error('Search cancelled');
            error.code = 'ERR_CANCELED';
            reject(error);
          };
          controller.signal.addEventListener('abort', handleAbort, { once: true });
        });
        const deadline = new Promise((_, reject) => {
          timeout = setTimeout(() => {
            const error = new Error('Search timed out');
            error.code = 'SEARCH_TIMEOUT';
            reject(error);
            controller.abort();
          }, SEARCH_TIMEOUT_MS);
          this.requestTimer = timeout;
        });
        const response = await Promise.race([
          axios.get('/search/', { params: { q: query }, signal: controller.signal, timeout: SEARCH_TIMEOUT_MS }),
          deadline,
          cancelled,
        ]);
        if (requestId !== this.requestId) return;
        this.items = [...localSearchResults(this.$store.state.apps?.apps, query), ...remoteSearchResults(response.data)];
        this.activeIndex = Math.min(this.activeIndex, this.items.length - 1);
      } catch (error) {
        if (requestId !== this.requestId) return;
        this.error = ['SEARCH_TIMEOUT', 'ECONNABORTED', 'ETIMEDOUT'].includes(error?.code)
          ? 'Search timed out. Try again.'
          : 'Templates and DockerHub search are unavailable. Try again.';
      } finally {
        clearTimeout(timeout);
        controller.signal.removeEventListener('abort', handleAbort);
        if (requestId === this.requestId) {
          this.isLoading = false;
          this.requestTimer = this.requestController = null;
        }
      }
    },
    retrySearch() { this.scheduleSearch(true); },
    clearSearch() {
      this.updateQuery('');
      this.$refs.input.focus();
    },
    async selectResult(item) {
      if (this.selectionRequestId === this.requestId) return;
      const destination = searchDestination(item);
      if (!destination) return;
      this.cancelSearch();
      const requestId = this.requestId;
      this.selectionRequestId = requestId;
      this.isLoading = false;
      try {
        const failure = await this.$router.push(destination);
        if (requestId !== this.requestId) return;
        if (isNavigationFailure(failure)) {
          this.error = 'Could not open the result. Try again.';
          return;
        }
        this.updateQuery('');
        this.isOpen = false;
        this.$emit('selected');
      } catch {
        if (requestId === this.requestId) this.error = 'Could not open the result. Try again.';
      } finally {
        if (this.selectionRequestId === requestId) this.selectionRequestId = null;
      }
    },
    handleKeydown(event) {
      if (event.isComposing) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        this.isOpen = false;
        this.activeIndex = -1;
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        this.isOpen = true;
        if (!this.items.length) return;
        const step = event.key === 'ArrowDown' ? 1 : -1;
        this.activeIndex = this.activeIndex < 0
          ? (step > 0 ? 0 : this.items.length - 1)
          : (this.activeIndex + step + this.items.length) % this.items.length;
        this.$nextTick(() => {
          this.$refs.root.querySelector(`#${this.searchId}-option-${this.activeIndex}`)?.scrollIntoView({ block: 'nearest' });
        });
      } else if (event.key === 'Enter' && this.isOpen && this.items[this.activeIndex]) {
        event.preventDefault();
        this.selectResult(this.items[this.activeIndex]);
      } else if (event.key === 'Tab') {
        this.isOpen = false;
      }
    },
    handleOutside(event) {
      if (!this.$refs.root.contains(event.target)) this.isOpen = false;
    },
    handleFocusOut(event) {
      if (!this.$refs.root.contains(event.relatedTarget)) this.isOpen = false;
    },
  },
};
</script>

<style scoped>
.search-container { position: relative; width: 100%; min-width: 0; color: var(--yp-text, #fff); }
.search-field { position: relative; }
.search-input { width: 100%; min-height: 44px; padding: 8px 40px 8px 12px; border: 1px solid var(--yp-border, #475569); border-radius: 6px; background: var(--yp-surface, #1a1d2e); color: inherit; font-size: 16px; }
.search-input:focus-visible { outline: 2px solid #64b5f6; outline-offset: 1px; }
.search-clear { position: absolute; right: 0; top: 0; width: 40px; height: 44px; font-size: 24px; }
.search-dropdown { position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 100; max-height: min(500px, 60vh); overflow-y: auto; background: var(--yp-surface, #1a1d2e); border: 1px solid var(--yp-border, #475569); border-radius: 8px; box-shadow: 0 8px 24px #0006; }
.section-header { padding: 8px 12px; color: var(--yp-muted, #aebbd0); font-size: 12px; font-weight: 600; }
.search-item { display: flex; flex-direction: column; text-align: left; width: 100%; min-height: 44px; padding: 10px 12px; overflow-wrap: anywhere; }
.search-item:hover, .search-item-active { background: var(--yp-surface-2, #2d3548); }
.item-title { font-size: 14px; }
.item-description { font-size: 12px; color: var(--yp-muted, #aebbd0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.search-status { padding: 12px; font-size: 13px; color: var(--yp-muted, #aebbd0); }
.search-retry { margin: 0 12px 12px; padding: 10px 12px; min-height: 44px; border: 1px solid var(--yp-border, #475569); border-radius: 4px; }
.search-retry:focus-visible, .search-clear:focus-visible { outline: 2px solid #64b5f6; }
</style>
