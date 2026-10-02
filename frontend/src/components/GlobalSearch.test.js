import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Vue from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import axios from 'axios';
import GlobalSearch from './GlobalSearch.vue';
import globalSource from './GlobalSearch.vue?raw';
import UnifiedSearch from './UnifiedSearch.vue';
import unifiedSource from './UnifiedSearch.vue?raw';
import SearchBox from './SearchBox.vue';
import searchSource from './SearchBox.vue?raw';
import { SEARCH_DELAY_MS, SEARCH_TIMEOUT_MS } from '@/utils/search';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));

// Mount real components and compiled templates through Vue's host renderer.
// Nodes expose rendered attributes and handlers without another DOM dependency.
const mountedApps = [];
function nodes(node) {
  return [node, ...(node.children || []).flatMap(nodes)];
}
function remove(node) {
  const index = node.parent?.children.indexOf(node);
  if (index >= 0) node.parent.children.splice(index, 1);
  node.parent = null;
}
const renderer = Vue.createRenderer({
  createElement(type) {
    const node = {
      type, props: {}, children: [], style: {},
      focus: vi.fn(() => { document.activeElement = node; }),
      scrollIntoView: vi.fn(),
      contains: target => nodes(node).includes(target),
      querySelector: selector => nodes(node).find(child => child.props?.id === selector.slice(1)),
    };
    return node;
  },
  createText: text => ({ type: 'text', text }),
  createComment: text => ({ type: 'comment', text }),
  setText: (node, text) => { node.text = text; },
  setElementText: (node, text) => { node.text = text; node.children = []; },
  patchProp: (node, key, previous, value) => { node.props[key] = value; },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1],
  insert(node, parent, anchor) {
    if (node.parent) remove(node);
    node.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node);
  },
  remove,
});
const compile = source => Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
const searchComponent = { ...SearchBox, render: compile(searchSource) };

function mountSearch(Component = GlobalSearch, source = globalSource, apps = [], props = {}) {
  const root = { children: [] };
  const warnings = [];
  const router = { push: vi.fn().mockResolvedValue() };
  const input = vi.fn();
  const selected = vi.fn();
  const app = renderer.createApp({
    ...Component, components: { SearchBox: searchComponent }, render: compile(source),
  }, { onInput: input, onSelected: selected, ...props });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  app.config.globalProperties.$store = { state: { apps: { apps } } };
  app.config.globalProperties.$router = router;
  app.config.warnHandler = message => warnings.push(message);
  const vm = app.mount(root);
  mountedApps.push(app);
  return {
    app, vm, search: app._instance.subTree.component.proxy, root, warnings, router, input, selected,
    inputNode: () => nodes(root).find(node => node.type === 'input'),
    options: () => nodes(root).filter(node => node.props?.role === 'option'),
    status: () => nodes(root).find(node => node.props?.role === 'status'),
    retry: () => nodes(root).find(node => node.props?.class === 'search-retry'),
  };
}
async function type(mounted, value) {
  mounted.inputNode().props.onInput({ target: { value } });
  await Vue.nextTick();
}
async function key(mounted, key, extra = {}) {
  const event = { key, preventDefault: vi.fn(), ...extra };
  mounted.inputNode().props.onKeydown(event);
  await Vue.nextTick();
  return event;
}
async function settle() {
  await vi.advanceTimersByTimeAsync(0);
  await Vue.nextTick();
}
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const text = node => node.type === 'comment' ? '' : [node.text || '', ...(node.children || []).map(text)].join('');

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.stubGlobal('document', { addEventListener: vi.fn(), removeEventListener: vi.fn(), activeElement: null });
  axios.get.mockReset().mockResolvedValue({ data: { templates: [], dockerhub: [] } });
});
afterEach(() => {
  mountedApps.splice(0).forEach(app => app.unmount());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe.each([
  ['global search', GlobalSearch, globalSource],
  ['application list search', UnifiedSearch, unifiedSource],
])('%s rendered search', (name, Component, source) => {
  it('selects a full DockerHub repository using arrows and Enter, then clears', async () => {
    axios.get.mockResolvedValueOnce({ data: { dockerhub: [{ full_name: 'linuxserver/nginx' }] } });
    const mounted = mountSearch(Component, source);
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    expect(mounted.warnings).toEqual([]);
    expect(mounted.options()).toHaveLength(1);
    expect(mounted.inputNode().props['aria-expanded']).toBe(true);
    const event = await key(mounted, 'ArrowDown');
    expect(event.preventDefault).toHaveBeenCalled();
    expect(mounted.options()[0].props['aria-selected']).toBe(true);
    expect(mounted.inputNode().props['aria-activedescendant']).toBe(mounted.options()[0].props.id);
    expect(mounted.options()[0].scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
    await key(mounted, 'Enter');
    await settle();
    expect(mounted.router.push).toHaveBeenCalledWith({ path: '/apps/deploy', query: { image: 'linuxserver/nginx' } });
    expect(mounted.inputNode().props.value).toBe('');
    expect(mounted.inputNode().props['aria-expanded']).toBe(false);
    if (Component === GlobalSearch) expect(mounted.selected).toHaveBeenCalled();
    else expect(mounted.input).toHaveBeenLastCalledWith('');
  });

  it('shows an API error, retains usable local matches and retries through the rendered button', async () => {
    axios.get.mockRejectedValueOnce(new Error('network failed'));
    const mounted = mountSearch(Component, source, [{ name: 'nginx', Config: { Image: 'nginx:alpine' } }]);
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    expect(text(mounted.status())).toContain('unavailable');
    expect(text(mounted.status())).not.toContain('No results');
    expect(mounted.options()).toHaveLength(1);
    axios.get.mockResolvedValueOnce({ data: { templates: [{ id: 7, title: 'Nginx template' }] } });
    mounted.retry().props.onClick();
    await settle();
    expect(mounted.retry()).toBeUndefined();
    expect(mounted.options()).toHaveLength(2);
    await mounted.options()[1].props.onClick();
    await settle();
    expect(mounted.router.push).toHaveBeenCalledWith({ name: 'Deploy', params: { appId: 7 } });
  });
});

describe('shared search cancellation and accessibility', () => {
  it('emits list filters immediately, including short queries, and clears from the button', async () => {
    const mounted = mountSearch(UnifiedSearch, unifiedSource);
    await type(mounted, 'n');
    expect(mounted.input).toHaveBeenLastCalledWith('n');
    expect(text(mounted.status())).toContain('at least 2');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    expect(axios.get).not.toHaveBeenCalled();
    nodes(mounted.root).find(node => node.props?.['aria-label'] === 'Clear search').props.onClick();
    await Vue.nextTick();
    expect(mounted.input).toHaveBeenLastCalledWith('');
    expect(mounted.inputNode().focus).toHaveBeenCalled();
  });

  it('wraps arrows through all source groups, closes on Escape and ignores Enter when closed', async () => {
    axios.get.mockResolvedValueOnce({ data: {
      templates: [{ id: 7, title: 'Nginx template' }], dockerhub: [{ full_name: 'nginx' }],
    } });
    const mounted = mountSearch(GlobalSearch, globalSource, [{ name: 'nginx' }]);
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    await key(mounted, 'ArrowUp');
    expect(mounted.options()[2].props['aria-selected']).toBe(true);
    await key(mounted, 'ArrowDown');
    expect(mounted.options()[0].props['aria-selected']).toBe(true);
    await key(mounted, 'Escape');
    expect(mounted.inputNode().props['aria-expanded']).toBe(false);
    expect(mounted.inputNode().props['aria-activedescendant']).toBeUndefined();
    await key(mounted, 'Enter');
    expect(mounted.router.push).not.toHaveBeenCalled();
    await key(mounted, 'ArrowDown', { isComposing: true });
    expect(mounted.inputNode().props['aria-expanded']).toBe(false);
  });

  it('navigates a local app selected through its rendered row', async () => {
    const mounted = mountSearch(GlobalSearch, globalSource, [{ name: 'web', Config: { Image: 'nginx:alpine' } }]);
    await type(mounted, 'nginx');
    await mounted.options()[0].props.onClick();
    await settle();
    expect(mounted.router.push).toHaveBeenCalledWith({ path: '/apps/web/info' });
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('aborts the previous request and ignores stale successes without ending the newer loading state', async () => {
    const first = deferred();
    const second = deferred();
    axios.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const mounted = mountSearch();
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    const firstSignal = axios.get.mock.calls[0][1].signal;
    await type(mounted, 'redis');
    expect(firstSignal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    first.resolve({ data: { dockerhub: [{ full_name: 'nginx' }] } });
    await settle();
    expect(mounted.options()).toHaveLength(0);
    expect(text(mounted.status())).toContain('Searching');
    second.resolve({ data: { dockerhub: [{ full_name: 'redis' }] } });
    await settle();
    expect(text(mounted.options()[0])).toBe('redis');
    expect(text(mounted.status())).not.toContain('Searching');
  });

  it('ignores a stale error after a newer successful search', async () => {
    const first = deferred();
    axios.get.mockReturnValueOnce(first.promise).mockResolvedValueOnce({ data: { dockerhub: [{ full_name: 'redis' }] } });
    const mounted = mountSearch();
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    await type(mounted, 'redis');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    first.reject(new Error('old network failure'));
    await settle();
    expect(text(mounted.options()[0])).toBe('redis');
    expect(mounted.retry()).toBeUndefined();
  });

  it('cancels debounce and in-flight searches when the query becomes short', async () => {
    const response = deferred();
    axios.get.mockReturnValueOnce(response.promise);
    const mounted = mountSearch();
    await type(mounted, 'nginx');
    await type(mounted, 'n');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    expect(axios.get).not.toHaveBeenCalled();
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    const signal = axios.get.mock.calls[0][1].signal;
    await type(mounted, '');
    expect(signal.aborted).toBe(true);
    response.resolve({ data: { dockerhub: [{ full_name: 'nginx' }] } });
    await settle();
    expect(mounted.options()).toHaveLength(0);
    expect(text(mounted.status())).toContain('at least 2');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('times out an unresponsive request, aborts it and permits recovery', async () => {
    axios.get.mockReturnValueOnce(new Promise(() => {}));
    const mounted = mountSearch();
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    const signal = axios.get.mock.calls[0][1].signal;
    await vi.advanceTimersByTimeAsync(SEARCH_TIMEOUT_MS);
    expect(signal.aborted).toBe(true);
    expect(text(mounted.status())).toContain('timed out');
    expect(text(mounted.status())).not.toContain('Searching');
    axios.get.mockResolvedValueOnce({ data: { dockerhub: [{ full_name: 'nginx' }] } });
    mounted.retry().props.onClick();
    await settle();
    expect(mounted.options()).toHaveLength(1);
    expect(mounted.retry()).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('treats a malformed API payload as an error while retaining local results', async () => {
    axios.get.mockResolvedValueOnce({ data: { dockerhub: { error: 'upstream failed' } } });
    const mounted = mountSearch(GlobalSearch, globalSource, [{ name: 'nginx' }]);
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    expect(mounted.options()).toHaveLength(1);
    expect(text(mounted.status())).toContain('unavailable');
    expect(mounted.retry()).toBeDefined();
  });

  it.each(['debounce', 'request'])('cleans up %s work and listeners when removed', async phase => {
    const response = deferred();
    axios.get.mockReturnValueOnce(response.promise);
    const mounted = mountSearch();
    await type(mounted, 'nginx');
    if (phase === 'request') await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    const signal = axios.get.mock.calls[0]?.[1].signal;
    mounted.app.unmount();
    mountedApps.splice(mountedApps.indexOf(mounted.app), 1);
    if (signal) expect(signal.aborted).toBe(true);
    response.resolve({ data: { dockerhub: [{ full_name: 'nginx' }] } });
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS + SEARCH_TIMEOUT_MS);
    if (phase === 'debounce') expect(axios.get).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    expect(document.removeEventListener).toHaveBeenCalledWith('pointerdown', expect.any(Function));
    expect(nodes(mounted.root).filter(node => node.props?.role === 'option')).toHaveLength(0);
  });

  it.each(['clear', 'unmount'])('settles cancelled transport work after %s even when the transport ignores abort', async action => {
    axios.get.mockReturnValueOnce(new Promise(() => {}));
    const mounted = mountSearch();
    const fetch = vi.spyOn(mounted.search, 'fetchResults');
    await type(mounted, 'nginx');
    await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
    let settled = false;
    fetch.mock.results[0].value.then(() => { settled = true; });
    if (action === 'clear') await type(mounted, '');
    else {
      mounted.app.unmount();
      mountedApps.splice(mountedApps.indexOf(mounted.app), 1);
    }
    await settle();
    expect(settled).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('preserves the query and reports a resolved Vue Router navigation failure', async () => {
    const router = createRouter({
      history: createMemoryHistory(), routes: [{ path: '/blocked', component: {} }],
    });
    router.beforeEach(() => false);
    const failure = await router.push('/blocked');
    const mounted = mountSearch(GlobalSearch, globalSource, [{ name: 'nginx' }]);
    mounted.router.push.mockResolvedValueOnce(failure);
    await type(mounted, 'nginx');
    await mounted.options()[0].props.onClick();
    await settle();
    expect(mounted.inputNode().props.value).toBe('nginx');
    expect(text(mounted.status())).toContain('Could not open');
    expect(mounted.inputNode().props['aria-expanded']).toBe(true);
    expect(mounted.selected).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'])('ignores delayed navigation %s after typing a newer query and suppresses duplicate selection', async outcome => {
    const navigation = deferred();
    const mounted = mountSearch(GlobalSearch, globalSource, [{ name: 'nginx' }]);
    mounted.router.push.mockReturnValueOnce(navigation.promise);
    await type(mounted, 'nginx');
    const option = mounted.options()[0];
    const selected = option.props.onClick();
    option.props.onClick();
    expect(mounted.router.push).toHaveBeenCalledTimes(1);
    await type(mounted, 'redis');
    if (outcome === 'resolve') navigation.resolve();
    else navigation.reject(new Error('navigation failed'));
    await selected;
    await settle();
    expect(mounted.inputNode().props.value).toBe('redis');
    expect(mounted.inputNode().props['aria-expanded']).toBe(true);
    expect(text(mounted.status())).toContain('Searching');
    expect(mounted.selected).not.toHaveBeenCalled();
  });

  it('closes only the search whose own container receives an outside interaction', async () => {
    const first = mountSearch();
    const second = mountSearch(UnifiedSearch, unifiedSource, [], { autofocus: true });
    await type(first, 'nginx');
    await type(second, 'redis');
    expect(first.inputNode().props['aria-controls']).not.toBe(second.inputNode().props['aria-controls']);
    const listeners = document.addEventListener.mock.calls.map(call => call[1]);
    listeners.forEach(listener => listener({ target: first.inputNode() }));
    await Vue.nextTick();
    expect(first.inputNode().props['aria-expanded']).toBe(true);
    expect(second.inputNode().props['aria-expanded']).toBe(false);
    await key(first, 'Tab');
    expect(first.inputNode().props['aria-expanded']).toBe(false);
    expect(second.inputNode().focus).toHaveBeenCalled();
  });
});
