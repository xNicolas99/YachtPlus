import { afterEach, describe, expect, it, vi } from 'vitest';
import * as Vue from 'vue';
import AsyncFeature from './AsyncFeature.vue';
import source from './AsyncFeature.vue?raw';

const apps = [];
const renderer = Vue.createRenderer({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: 'text', text }),
  createComment: text => ({ type: 'comment', text }),
  setText: (node, text) => { node.text = text; },
  setElementText: (node, text) => { node.text = text; node.children = []; },
  patchProp: (node, key, previous, value) => { node.props[key] = value; },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1],
  insert(node, parent, anchor) {
    if (node.parent) {
      const index = node.parent.children.indexOf(node);
      if (index >= 0) node.parent.children.splice(index, 1);
    }
    node.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node);
  },
  remove(node) {
    const index = node.parent?.children.indexOf(node);
    if (index >= 0) node.parent.children.splice(index, 1);
    node.parent = null;
  }
});
function mount(loader) {
  const close = vi.fn();
  const root = { children: [] };
  const render = Vue.compile(source.match(/<template>([\s\S]*?)<\/template>/)[1]);
  const app = renderer.createApp({ ...AsyncFeature, render }, {
    name: 'Terminal', loader, timeout: 1000, containerId: 'container-123', visible: true, onClose: close
  });
  for (const name of ['VDialog', 'VCard', 'VCardTitle', 'VCardText', 'VCardActions', 'VAlert', 'VBtn']) {
    app.component(name, { setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.()) });
  }
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [ ...(node.type === type ? [node] : []), ...(node.children || []).flatMap(child => nodes(type, child)) ];
  const text = (node = root) => [node.text || '', ...(node.children || []).map(text)].join(' ');
  return { vm, nodes, text, close, app };
}
const flush = async () => { for (let i = 0; i < 8; i++) { await Promise.resolve(); await Vue.nextTick(); } };
const loaded = { props: ['containerId', 'visible'], emits: ['close'], setup: (props, { emit }) => () => Vue.h('terminal', { id: props.containerId, visible: props.visible, onClose: () => emit('close') }) };
afterEach(() => { apps.splice(0).forEach(app => app.unmount()); vi.useRealTimers(); });

describe('lazy feature loading failsafe', () => {
  it('renders a loading state then the feature with its props and close event', async () => {
    const mounted = mount(vi.fn().mockResolvedValue({ default: loaded }));
    expect(mounted.text()).toContain('Loading Terminal');
    await flush();
    expect(mounted.nodes('terminal')[0].props).toMatchObject({ id: 'container-123', visible: true });
    mounted.nodes('terminal')[0].props.onClose();
    expect(mounted.close).toHaveBeenCalledOnce();
  });
  it('shows a sanitized failure and lets the user retry successfully', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new Error('secret-host/asset')).mockResolvedValueOnce({ default: loaded });
    const mounted = mount(loader);
    await flush();
    expect(mounted.text()).toContain('could not be loaded');
    expect(mounted.text()).not.toContain('secret-host');
    mounted.nodes('VBtn')[0].props.onClick();
    await flush();
    expect(loader).toHaveBeenCalledTimes(2);
    expect(mounted.nodes('terminal')).toHaveLength(1);
  });
  it('blocks repeated clicks while the import is pending', async () => {
    const loader = vi.fn(() => new Promise(() => {}));
    const mounted = mount(loader);
    mounted.vm.load();
    mounted.vm.load();
    await flush();
    expect(loader).toHaveBeenCalledOnce();
    expect(mounted.nodes('VBtn')).toHaveLength(1);
  });
  it('times out and ignores a late result after retry', async () => {
    vi.useFakeTimers();
    let resolveFirst;
    const loader = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; })).mockResolvedValueOnce({ default: loaded });
    const mounted = mount(loader);
    await flush();
    await vi.advanceTimersByTimeAsync(1000);
    await flush();
    expect(mounted.text()).toContain('could not be loaded');
    mounted.nodes('VBtn')[0].props.onClick();
    await flush();
    resolveFirst({ default: { render: () => Vue.h('stale') } });
    await flush();
    expect(mounted.nodes('terminal')).toHaveLength(1);
    expect(mounted.nodes('stale')).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each([undefined, { default: 'bad' }, {}])('rejects malformed feature modules (%j)', async module => {
    const mounted = mount(vi.fn().mockResolvedValue(module));
    await flush();
    expect(mounted.nodes('VAlert')).toHaveLength(1);
  });
  it('closing during loading cancels timers and never mounts a late feature', async () => {
    vi.useFakeTimers();
    let resolve;
    const mounted = mount(() => new Promise(done => { resolve = done; }));
    await flush();
    mounted.nodes('VBtn')[0].props.onClick();
    mounted.app.unmount();
    resolve({ default: loaded });
    await flush();
    expect(mounted.close).toHaveBeenCalledOnce();
    expect(mounted.vm.feature).toBe(null);
    expect(vi.getTimerCount()).toBe(0);
  });
});
