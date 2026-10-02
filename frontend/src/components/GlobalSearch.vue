<template>
  <SearchBox label="Search Apps, Templates and DockerHub" @selected="$emit('selected')" />
</template>

<script>
import SearchBox from './SearchBox.vue';

export default {
  name: 'GlobalSearch',
  components: { SearchBox },
  emits: ['selected'],
};
</script>
