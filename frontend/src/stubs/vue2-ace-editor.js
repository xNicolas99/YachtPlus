import { h } from 'vue';

export default {
    name: 'Vue2AceEditorShim',
    // Support both Vue 2 (value) and Vue 3 (modelValue) props
    props: ['value', 'modelValue', 'lang', 'theme', 'height', 'width', 'options'],
    emits: ['update:value', 'update:modelValue', 'input', 'init'],
    setup(props, { emit }) {
        return () => h('textarea', {
            // Prefer modelValue (Vue 3), fallback to value (Vue 2)
            value: props.modelValue !== undefined ? props.modelValue : props.value,
            style: {
                width: props.width || '100%',
                height: props.height || '300px',
                fontFamily: 'monospace',
                backgroundColor: '#1e1e1e',
                color: '#d4d4d4',
                border: '1px solid #333',
                padding: '10px'
            },
            onInput: (e) => {
                const val = e.target.value;
                // Emit all possible events to ensure compatibility
                emit('input', val);             // Vue 2 standard
                emit('update:value', val);      // Vue 2 sync/v-model
                emit('update:modelValue', val); // Vue 3 v-model
            }
        });
    }
};
