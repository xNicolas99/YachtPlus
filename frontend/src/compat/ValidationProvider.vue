<template>
  <Field v-bind="$attrs" :rules="rules" v-slot="slotProps">
    <slot
      :errors="slotProps.errorMessage ? [slotProps.errorMessage] : []"
      :valid="slotProps.meta.valid"
      :invalid="!slotProps.meta.valid"
      :pristine="!slotProps.meta.dirty"
      :dirty="slotProps.meta.dirty"
      v-bind="slotProps"
    ></slot>
  </Field>
</template>

<script>
import { Field } from 'vee-validate';

export default {
  name: 'ValidationProvider',
  components: { Field },
  props: {
    rules: {
      type: [String, Object],
      default: undefined
    }
  }
}
</script>
