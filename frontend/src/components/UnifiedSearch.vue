<template>
  <SearchBox label="Filter Apps and search Templates or DockerHub" @input="$emit('input', $event)" />
</template>

<script>
import SearchBox from './SearchBox.vue';

export default {
  name: 'UnifiedSearch',
  components: { SearchBox },
  emits: ['input'],
};
</script>
