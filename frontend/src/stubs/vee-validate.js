import { h } from 'vue';

export const ValidationProvider = {
    name: 'ValidationProvider',
    props: ['rules', 'vid', 'name', 'slim', 'mode', 'immediate'],
    setup(props, { slots }) {
        return () => slots.default ? slots.default({
            errors: [],
            valid: true,
            invalid: false,
            pristine: true,
            dirty: false,
            touched: false,
            untouched: true,
            pending: false,
            validated: true,
            passed: true,
            failed: false,
            ariaInput: {},
            ariaMsg: {}
        }) : null;
    }
};

export const ValidationObserver = {
    name: 'ValidationObserver',
    setup(props, { slots }) {
        return () => slots.default ? slots.default({
            valid: true,
            invalid: false,
            pristine: true,
            dirty: false,
            touched: false,
            untouched: true,
            handleSubmit: async (fn) => { await fn(); },
            reset: () => {},
            validate: () => Promise.resolve(true)
        }) : null;
    }
};

export const extend = () => {};
export const setInteractionMode = () => {};
