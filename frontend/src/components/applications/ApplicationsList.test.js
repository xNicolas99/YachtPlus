import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Vue from 'vue';
import { createStore } from 'vuex';
import ApplicationsList from './ApplicationsList.vue';
import source from './ApplicationsList.vue?raw';
import { containerViewStorageKey, normalizeContainerPreferences } from '@/utils/containerViews';

const mountedApps = [];
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
  },
});
const inventory = [
  { Id: '1', name: 'web', State: { Status: 'running', Health: { Status: 'unhealthy' } }, Config: { Image: 'nginx', Labels: { 'com.docker.compose.project': 'production' } }, isUpdatable: true },
  { Id: '2', name: 'database', State: { Status: 'running', Health: { Status: 'healthy' } }, Config: { Image: 'postgres', Labels: { 'com.docker.compose.project': 'production' } } },
  { Id: '3', name: 'cache', State: { Status: 'exited' }, Config: { Image: 'redis', Labels: {} } },
];
let storage;
beforeEach(() => {
  storage = new Map();
  vi.stubGlobal('localStorage', {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
  });
  vi.stubGlobal('location', { hostname: 'localhost' });
});
afterEach(() => { mountedApps.splice(0).forEach(app => app.unmount()); vi.unstubAllGlobals(); });
const flush = async () => { for (let index = 0; index < 5; index++) { await Vue.nextTick(); await Promise.resolve(); } };

function mount(query = {}, readResult = true) {
  const store = createStore({ modules: {
    auth: { namespaced: true, state: () => ({ username: 'alice' }) },
    snackbar: { namespaced: true, mutations: { setErr: vi.fn() } },
    apps: {
      namespaced: true,
      state: () => ({ apps: structuredClone(inventory), updatable: [], isLoading: false, isLoadingValue: null, action: '' }),
      actions: { readApps: vi.fn().mockResolvedValue(readResult), AppAction: vi.fn(), AppUpdate: vi.fn(), checkAppUpdate: vi.fn() },
    },
  } });
  const route = Vue.reactive({ path: '/apps', query });
  const router = { push: vi.fn().mockResolvedValue(), replace: vi.fn(({ query }) => {
    route.query = query;
    return Promise.resolve();
  }) };
  const app = renderer.createApp({
    ...ApplicationsList,
    components: {
      ContainerLogs: { render: () => Vue.h('logs') },
      AsyncFeature: { render: () => Vue.h('terminal') },
      UnifiedSearch: { props: ['modelValue'], emits: ['update:modelValue'], setup: (props, { emit }) => () => Vue.h('search', { value: props.modelValue, onInput: value => emit('update:modelValue', value) }) },
    },
    render: Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]),
  });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const name of [
    'VCard', 'VCardTitle', 'VCardSubtitle', 'VCardText', 'VCardActions', 'VSpacer',
    'VBtn', 'VMenu', 'VIcon', 'VList', 'VListItem', 'VListItemTitle', 'VListSubheader',
    'VAlert', 'VDivider', 'VTooltip', 'VCheckbox', 'VChip', 'VSelect', 'VTextField',
  ]) app.component(name, { setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.()) });
  app.component('VDialog', { props: ['modelValue'], setup: (props, { attrs, slots }) => () => Vue.h('VDialog', { ...attrs, modelValue: props.modelValue }, props.modelValue ? slots.default?.() : []) });
  app.component('VDataTable', { setup: (_, { attrs }) => () => Vue.h('VDataTable', attrs) });
  app.use(store);
  app.config.globalProperties.$route = route;
  app.config.globalProperties.$router = router;
  const root = { children: [] };
  const vm = app.mount(root);
  mountedApps.push(app);
  const nodes = (type, node = root) => [ ...(node.type === type ? [node] : []), ...(node.children || []).flatMap(child => nodes(type, child)) ];
  return { vm, store, route, router, nodes, table: () => nodes('VDataTable')[0].props };
}

describe('saved container views', () => {
  it('restores filters, visible search text and column identifiers for the current account', async () => {
    storage.set(containerViewStorageKey('alice'), JSON.stringify({ version: 1, current: { search: 'web', columns: ['name', 'project'], health: 'unhealthy' } }));
    const mounted = mount();
    await flush();
    expect(mounted.nodes('search')[0].props.value).toBe('web');
    expect(mounted.table().items.map(item => item.name)).toEqual(['web']);
    expect(mounted.table().headers.map(header => header.key)).toEqual(['name', 'project']);
    expect(mounted.route.query).toMatchObject({ health: 'unhealthy', q: 'web' });
  });

  it('applies direct dashboard queries and follows route changes without retaining unrelated saved filters', async () => {
    storage.set(containerViewStorageKey('alice'), JSON.stringify({ version: 1, current: { search: 'cache', columns: ['name', 'health'], status: 'stopped' } }));
    const mounted = mount({ health: 'unhealthy', status: 'running' });
    await flush();
    expect(mounted.table().items.map(item => item.name)).toEqual(['web']);
    expect(mounted.vm.search).toBe('');
    mounted.route.query = { status: 'stopped' };
    await flush();
    expect(mounted.table().items.map(item => item.name)).toEqual(['cache']);
    mounted.route.query = {};
    await flush();
    expect(mounted.table().items).toHaveLength(3);
    expect(mounted.table().headers.map(header => header.key)).toEqual(['name', 'health']);
  });

  it('filters through rendered controls and clears the visible search while keeping selected columns', async () => {
    const mounted = mount();
    mounted.nodes('VSelect').find(node => node.props.label === 'Status').props['onUpdate:modelValue']('running');
    mounted.nodes('VSelect').find(node => node.props.label === 'Health').props['onUpdate:modelValue']('healthy');
    await flush();
    expect(mounted.table().items.map(item => item.name)).toEqual(['database']);
    mounted.nodes('search')[0].props.onInput('postgres');
    mounted.vm.selectedColumnKeys = ['name', 'project'];
    await flush();
    expect(mounted.vm.activeFilters).toHaveLength(3);
    mounted.vm.clearFilters();
    await flush();
    expect(mounted.nodes('search')[0].props.value).toBe('');
    expect(mounted.table().items).toHaveLength(3);
    expect(mounted.table().headers.map(header => header.key)).toEqual(['name', 'project']);
    expect(mounted.route.query).toEqual({});
  });

  it('saves independent snapshots, restores them, replaces named views and deletes them', async () => {
    const mounted = mount();
    mounted.vm.view.health = 'unhealthy';
    mounted.vm.viewName = 'Production alerts';
    mounted.vm.saveNamedView();
    mounted.vm.view.health = 'healthy';
    expect(mounted.vm.savedViews[0].config.health).toBe('unhealthy');
    expect(mounted.vm.viewModified).toBe(true);
    mounted.vm.applySavedView('Production alerts');
    expect(mounted.vm.view.health).toBe('unhealthy');
    mounted.vm.view.health = 'healthy';
    mounted.vm.viewName = 'PRODUCTION ALERTS';
    mounted.vm.saveNamedView();
    expect(mounted.vm.savedViews).toHaveLength(1);
    expect(mounted.vm.savedViews[0].config.health).toBe('healthy');
    await flush();
    const stored = JSON.parse(storage.get(containerViewStorageKey('alice')));
    expect(stored.savedViews).toHaveLength(1);
    mounted.vm.deleteSavedView();
    expect(mounted.vm.selectedView).toBe('');
    expect(mounted.vm.savedViews).toEqual([]);
    expect(mounted.vm.view.health).toBe('healthy');
  });

  it('validates names and resets the current view without deleting saved views', async () => {
    const mounted = mount();
    mounted.vm.viewName = '   ';
    mounted.vm.saveNamedView();
    expect(mounted.vm.viewNameError).toContain('between 1 and 60');
    expect(mounted.vm.savedViews).toHaveLength(0);
    mounted.vm.viewName = 'Useful';
    mounted.vm.saveNamedView();
    mounted.vm.view.columns = ['name'];
    mounted.vm.view.stack = 'production';
    mounted.vm.resetView();
    await flush();
    expect(mounted.vm.view).toEqual(normalizeContainerPreferences().current);
    expect(mounted.vm.savedViews).toHaveLength(1);
    expect(mounted.vm.selectedView).toBe('');
  });

  it('retains usable in-memory views when browser storage is blocked', async () => {
    vi.stubGlobal('localStorage', { getItem() { throw new Error('Blocked'); }, setItem() { throw new Error('Blocked'); } });
    const mounted = mount();
    mounted.vm.view.health = 'unhealthy';
    await flush();
    expect(mounted.table().items.map(item => item.name)).toEqual(['web']);
    expect(mounted.vm.storageWarning).toContain('only last for this session');
  });

  it('shows the load error immediately when the store reports failure', async () => {
    const mounted = mount({}, false);
    await flush();
    expect(mounted.vm.loadError).toBe(true);
    expect(mounted.nodes('VDataTable')).toHaveLength(0);
  });

  it.each([false, true])('renders one removal confirmation and closes only after task success (%s)', async succeeded => {
    let finish;
    const mounted = mount();
    mounted.vm.AppAction = vi.fn().mockReturnValue(new Promise(resolve => { finish = resolve; }));
    mounted.vm.selectedApp = inventory[0];
    mounted.vm.removeDialog = true;
    const pending = mounted.vm.confirmRemove();
    await flush();
    const dialogs = mounted.nodes('VDialog').filter(node => node.props.modelValue);
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0].props.persistent).toBe(true);
    expect(mounted.vm.removing).toBe(true);
    await mounted.vm.confirmRemove();
    expect(mounted.vm.AppAction).toHaveBeenCalledExactlyOnceWith({ Name: 'web', Action: 'remove' });
    finish(succeeded);
    await pending;
    expect(mounted.vm.removeDialog).toBe(!succeeded);
    expect(mounted.vm.removing).toBe(false);
  });
});
