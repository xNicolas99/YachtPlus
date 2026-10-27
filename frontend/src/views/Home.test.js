import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Vue from 'vue';
import axios from 'axios';
import { runTrackedOperation } from '@/utils/operations';
import Home from './Home.vue';
import homeSource from './Home.vue?raw';
import ContainerCard from '@/components/ContainerCard.vue';
import cardSource from '@/components/ContainerCard.vue?raw';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock('@/utils/operations', () => ({ runTrackedOperation: vi.fn() }));
const apps = [];
const renderer = Vue.createRenderer({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: 'text', text }), createComment: text => ({ type: 'comment', text }),
  setText: (node, text) => { node.text = text; }, setElementText: (node, text) => { node.text = text; node.children = []; },
  patchProp: (node, key, previous, value) => { node.props[key] = value; }, parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1],
  insert(node, parent, anchor) {
    if (node.parent) { const old = node.parent.children.indexOf(node); if (old >= 0) node.parent.children.splice(old, 1); }
    node.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node);
  },
  remove(node) { const index = node.parent?.children.indexOf(node); if (index >= 0) node.parent.children.splice(index, 1); node.parent = null; },
});
const inventory = () => [{ Id: 'web-id', name: 'web', State: { Status: 'running' }, Config: { Image: 'web:latest' } }];
const overview = () => ({ containers: { total: 1, running: 1, stopped: 0, unhealthy: 0 }, projects: { total: 1 }, images: { total: 2, total_size: 4096 }, volumes: { total: 1, in_use: 1, unused: 0 }, networks: { total: 2, custom: 1, default: 1 } });
const readings = () => ({ web: { cpu_percent: 12.5, memory_percent: 25, memory_usage_mb: 32, memory_limit_mb: 128 } });
function respond(values = {}) {
  axios.get.mockImplementation(url => Promise.resolve({ data: ({ '/apps/': inventory(), '/dashboard/stats': overview(), '/containers/stats': readings(), ...values })[url] }));
}
function mount(component = Home, source = homeSource, { bootstrap = false, props = {} } = {}) {
  const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
  const options = component === Home ? { ...component, created: bootstrap ? component.created : undefined } : component;
  const app = renderer.createApp({ ...options, render, components: { ...component.components,
    PageHeader: { props: ['title', 'subtitle'], setup: (props, { slots }) => () => Vue.h('header', {}, [Vue.h('h1', props.title), slots.subtitle?.(), slots.actions?.()]) },
    ContainerCard: { props: ['container', 'stats', 'stale', 'loading', 'busy'], setup: props => () => Vue.h('container', { ...props }) },
  } }, props);
  for (const name of ['VMenu', 'VList', 'VListItem', 'VListItemTitle', 'VBtn', 'VIcon', 'VProgressLinear', 'VProgressCircular', 'VCard', 'VCardText', 'VDivider']) {
    app.component(name, { setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.()) });
  }
  app.component('VAlert', { setup: (_, { attrs, slots }) => () => Vue.h('VAlert', attrs, [slots.default?.(), slots.append?.()]) });
  app.component('RouterLink', { props: ['to'], setup: (props, { attrs, slots }) => () => Vue.h('a', { ...attrs, to: props.to }, slots.default?.()) });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  app.config.globalProperties.$store = { commit: vi.fn() };
  app.config.globalProperties.$router = { push: vi.fn() };
  const root = { children: [] };
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [...(node.type === type ? [node] : []), ...(node.children || []).flatMap(child => nodes(type, child))];
  const text = (node = root) => [node.text || '', ...(node.children || []).map(text)].join(' ');
  return { vm, app, nodes, text };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('window', { location: { hostname: 'docker.local' }, confirm: vi.fn().mockReturnValue(true) });
  vi.stubGlobal('document', { hidden: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  vi.stubGlobal('localStorage', { getItem: vi.fn().mockReturnValue(null), setItem: vi.fn() });
});
afterEach(() => { apps.splice(0).forEach(app => app.unmount()); vi.useRealTimers(); vi.unstubAllGlobals(); });
const flush = async () => { for (let i = 0; i < 8; i++) { await Promise.resolve(); await Vue.nextTick(); } };

describe('dashboard snapshots', () => {
  it('shows unknown values until a complete snapshot is verified', () => {
    const mounted = mount();
    expect(mounted.text()).toContain('No verified data available yet');
    expect(mounted.text()).not.toContain('No containers yet');
    expect(mounted.nodes('span').filter(node => node.props.class?.includes('yp-kpi-num')).every(node => node.text === '—')).toBe(true);
  });
  it('commits inventory, overview and readings together with a successful update time', async () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-27T08:00:00Z')); respond();
    const mounted = mount();
    await expect(mounted.vm.refresh()).resolves.toBe(true);
    await Vue.nextTick();
    expect(mounted.vm.inventory).toEqual(inventory());
    expect(mounted.vm.overview).toEqual(overview());
    expect(mounted.vm.stats.web).toMatchObject({ cpu_percent: 12.5, mem_percent: 25, mem_current: '32 MB', mem_total: '128 MB' });
    expect(mounted.vm.lastUpdatedAt).toBe(Date.now());
    expect(mounted.text()).toContain('Last successful update:');
    expect(mounted.text()).toContain('Connected');
    expect(axios.get).toHaveBeenCalledTimes(3);
    for (const [, config] of axios.get.mock.calls) expect(config).toMatchObject({ timeout: 15000, signal: expect.any(AbortSignal) });
  });
  it('retains the previous complete snapshot and marks it stale when a source fails', async () => {
    respond(); const mounted = mount(); await mounted.vm.refresh(); const previous = mounted.vm.lastUpdatedAt;
    axios.get.mockImplementation(url => url === '/dashboard/stats' ? Promise.reject(new Error('offline')) : Promise.resolve({ data: url === '/apps/' ? [] : {} }));
    await expect(mounted.vm.refresh()).resolves.toBe(false); await Vue.nextTick();
    expect(mounted.vm.inventory).toEqual(inventory());
    expect(mounted.vm.lastUpdatedAt).toBe(previous);
    expect(mounted.vm.isStale).toBe(true);
    expect(mounted.text()).toContain('from the last successful update and may be outdated');
    expect(mounted.nodes('container')[0].props.stale).toBe(true);
  });
  it('rejects degraded sources rather than publishing fabricated zero values', async () => {
    respond({ '/dashboard/stats': { ...overview(), availability: { containers: true, volumes: false } } }); const mounted = mount();
    await expect(mounted.vm.refresh()).resolves.toBe(false); await Vue.nextTick();
    expect(mounted.vm.lastUpdatedAt).toBeNull();
    expect(mounted.text()).toContain('Some resource or stack data is unavailable');
    expect(mounted.text()).not.toContain('No containers yet');
  });
  it('rejects incomplete successful responses', async () => {
    respond({ '/dashboard/stats': { containers: { total: 1 } } }); const mounted = mount();
    await expect(mounted.vm.refresh()).resolves.toBe(false);
    expect(mounted.vm.hasSnapshot).toBe(false); expect(mounted.vm.inventory).toEqual([]);
  });
  it('shares a pending refresh and never starts overlapping polls', async () => {
    const resolvers = [];
    axios.get.mockImplementation(url => new Promise(resolve => resolvers.push(() => resolve({ data: { '/apps/': inventory(), '/dashboard/stats': overview(), '/containers/stats': readings() }[url] }))));
    const mounted = mount(); const first = mounted.vm.refresh(); const second = mounted.vm.refresh();
    expect(first).toBe(second); expect(axios.get).toHaveBeenCalledTimes(3);
    resolvers.forEach(resolve => resolve()); await first;
  });
  it('provides links matching the container list filter contract', () => {
    const targets = mount().nodes('a').map(node => node.props.to);
    expect(targets).toContainEqual({ path: '/apps', query: { status: 'running' } });
    expect(targets).toContainEqual({ path: '/apps', query: { status: 'stopped' } });
    expect(targets).toContainEqual({ path: '/apps', query: { health: 'unhealthy' } });
  });
  it('puts unhealthy, restarting and failed containers before healthy containers', () => {
    const mounted = mount();
    mounted.vm.inventory = [inventory()[0], { name: 'failed', State: { Status: 'exited', ExitCode: 2 } }, { name: 'healthy', State: { Status: 'running', Health: { Status: 'healthy' } } }, { name: 'bad', State: { Status: 'running', Health: { Status: 'unhealthy' } } }];
    expect(mounted.vm.attentionContainers.map(container => container.name)).toEqual(['failed', 'bad']);
    expect(mounted.vm.sortedContainers.map(container => container.name)).toEqual(['bad', 'failed', 'healthy', 'web']);
  });
  it('recognizes health from Docker list summaries before inspect data is loaded', () => {
    const mounted = mount();
    mounted.vm.inventory = [{ name: 'unhealthy-summary', State: { Status: 'running' }, Status: 'Up 2 minutes (unhealthy)' }];
    expect(mounted.vm.attentionContainers.map(container => container.name)).toEqual(['unhealthy-summary']);
    const card = mount(ContainerCard, cardSource, { props: { container: mounted.vm.inventory[0] } });
    expect(card.text()).toContain('running · unhealthy');
    expect(card.text()).toContain('health check is failing');
  });
  it('keeps polling quiet while hidden, refreshes on return and cleans up timers', async () => {
    vi.useFakeTimers(); respond(); const mounted = mount(Home, homeSource, { bootstrap: true }); await flush(); axios.get.mockClear();
    document.hidden = true; await vi.advanceTimersByTimeAsync(5000); expect(axios.get).not.toHaveBeenCalled(); document.hidden = false;
    const visibility = document.addEventListener.mock.calls.find(([name]) => name === 'visibilitychange')[1]; visibility(); await flush();
    expect(axios.get).toHaveBeenCalledTimes(3); mounted.app.unmount(); expect(vi.getTimerCount()).toBe(0);
    expect(document.removeEventListener).toHaveBeenCalledWith('visibilitychange', visibility);
  });
  it('ignores late responses after leaving the dashboard', async () => {
    const resolvers = [];
    axios.get.mockImplementation(url => new Promise(resolve => resolvers.push(() => resolve({ data: { '/apps/': inventory(), '/dashboard/stats': overview(), '/containers/stats': readings() }[url] }))));
    const mounted = mount(); const pending = mounted.vm.refresh(); mounted.app.unmount();
    expect(axios.get.mock.calls[0][1].signal.aborted).toBe(true); resolvers.forEach(resolve => resolve()); await pending;
    expect(mounted.vm.lastUpdatedAt).toBeNull();
  });
});

describe('container cards', () => {
  it('shows an unhealthy reason, a keyboard-accessible details link and the snapshot label', () => {
    const mounted = mount(ContainerCard, cardSource, { props: { container: { name: 'web', State: { Status: 'running', Health: { Status: 'unhealthy' } } }, stale: true } });
    expect(mounted.text()).toContain('running · unhealthy'); expect(mounted.text()).toContain('health check is failing'); expect(mounted.text()).toContain('Snapshot');
    expect(mounted.nodes('a')[0].props.to).toEqual({ path: '/apps/web/info' }); expect(mounted.nodes('VProgressCircular')).toHaveLength(0); expect(mounted.text()).toContain('Usage unavailable');
  });
  it('distinguishes pending usage from unavailable usage without endless spinners', async () => {
    const mounted = mount(ContainerCard, cardSource, { props: { container: inventory()[0], loading: true } });
    expect(mounted.nodes('VProgressCircular')).toHaveLength(1); mounted.vm.$.props.loading = false; await Vue.nextTick();
    expect(mounted.nodes('VProgressCircular')).toHaveLength(0); expect(mounted.text()).toContain('Usage unavailable');
  });
});

describe('tracked dashboard actions', () => {
  it('records actions in Tasks and prevents duplicate submissions while waiting', async () => {
    let finish;
    runTrackedOperation.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    const mounted = mount();
    mounted.vm.refresh = vi.fn().mockResolvedValue(true);
    const pending = mounted.vm.handleContainerAction('restart', 'web');
    await mounted.vm.handleContainerAction('restart', 'web');
    expect(runTrackedOperation).toHaveBeenCalledExactlyOnceWith(axios, { kind: 'container.action', resource: 'web', action: 'restart' });
    expect(mounted.vm.pendingActions.web).toBe('restart');
    finish({ status: 'succeeded' });
    await pending;
    expect(mounted.vm.pendingActions.web).toBeUndefined();
    expect(mounted.vm.refresh).toHaveBeenCalledOnce();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('reports a failed task without showing success or refreshing away the snapshot', async () => {
    const error = new Error('Task failed');
    runTrackedOperation.mockRejectedValueOnce(error);
    const mounted = mount();
    mounted.vm.refresh = vi.fn();
    await mounted.vm.handleContainerAction('stop', 'web');
    expect(mounted.vm.$store.commit).toHaveBeenCalledExactlyOnceWith('snackbar/setErr', error);
    expect(mounted.vm.refresh).not.toHaveBeenCalled();
    expect(mounted.vm.pendingActions.web).toBeUndefined();
  });
});
