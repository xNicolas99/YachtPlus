<template>
  <Form ref="form" as="span" v-bind="$attrs" v-slot="slotProps">
    <slot v-bind="slotProps"></slot>
  </Form>
</template>

<script>
import { Form } from 'vee-validate';

export default {
  name: 'ValidationObserver',
  components: { Form },
  methods: {
    async validate() {
      const result = await this.$refs.form.validate();
      return result.valid;
    },
    async reset() {
      return this.$refs.form.resetForm();
    },
    setErrors(errors) {
      this.$refs.form.setErrors(errors);
    }
  }
}
</script>
