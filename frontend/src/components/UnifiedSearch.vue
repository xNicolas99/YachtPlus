<template>
  <SearchBox :model-value="modelValue" label="Filter containers and search Templates or DockerHub" @input="$emit('input', $event)" @update:model-value="$emit('update:modelValue', $event)" />
</template>

<script>
import SearchBox from './SearchBox.vue';

export default {
  name: 'UnifiedSearch',
  components: { SearchBox },
  props: { modelValue: { type: String, default: undefined } },
  emits: ['input', 'update:modelValue'],
};
</script>
