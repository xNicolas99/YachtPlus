<template>
  <header class="yp-page-header">
    <div class="yp-page-header__copy">
      <component :is="headingTag" class="yp-page-header__title" :class="{ 'yp-page-header__title--subsection': headingLevel > 1 }">{{ title }}</component>
      <p v-if="subtitle || $slots.subtitle" class="yp-page-header__subtitle">
        <slot name="subtitle">{{ subtitle }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="yp-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script>
export default {
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, default: "" },
    headingLevel: { type: Number, default: 1 }
  },
  computed: {
    headingTag() { return Number.isInteger(this.headingLevel) && this.headingLevel >= 1 && this.headingLevel <= 6 ? `h${this.headingLevel}` : "h1"; }
  }
};
</script>

<style scoped>
.yp-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px 24px;
  margin-bottom: 24px;
}
.yp-page-header__copy {
  flex: 1 1 240px;
  min-width: 0;
}
.yp-page-header__title {
  margin: 0;
  color: var(--yp-text);
  font-size: clamp(24px, 2.4vw, 30px);
  font-weight: 650;
  letter-spacing: -0.035em;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.yp-page-header__subtitle {
  margin: 6px 0 0;
  color: var(--yp-muted);
  font-size: 13px;
  line-height: 1.6;
}
.yp-page-header__title--subsection { font-size: 22px; }
.yp-page-header__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 100%;
}
@media (max-width: 600px) {
  .yp-page-header {
    align-items: flex-start;
    gap: 14px;
    margin-bottom: 20px;
  }
  .yp-page-header__copy,
  .yp-page-header__actions {
    flex-basis: 100%;
  }
}
</style>
