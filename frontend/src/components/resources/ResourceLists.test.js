import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import ImageList from './images/ImageList.vue';
import VolumeList from './volumes/VolumeList.vue';
import NetworkList from './networks/NetworkList.vue';
import * as Vue from 'vue';
import { createStore } from 'vuex';
import imageSource from './images/ImageList.vue?raw';
import networkSource from './networks/NetworkList.vue?raw';
import volumeSource from './volumes/VolumeList.vue?raw';
import Prune from '../serverSettings/Prune.vue';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

describe.each([
  [ImageList, 'image', 'nginx', 'pullDialog', 'pulling', 'writeImage'],
  [VolumeList, 'name', 'data', 'createDialog', 'creating', 'writeVolume'],
])('resource creation', (component, field, value, dialog, busy, action) => {
  it('retains user input and the open dialog after rejection', async () => {
    const ctx = { ...component.data(), [dialog]: true, form: { [field]: value }, [action]: vi.fn().mockResolvedValue(false) };
    await component.methods.submit.call(ctx);
    expect(ctx[dialog]).toBe(true);
    expect(ctx.form[field]).toBe(value);
    expect(ctx[busy]).toBe(false);
  });

  it('prevents a duplicate request and closes only after success', async () => {
    let resolve;
    const ctx = { ...component.data(), [dialog]: true, form: { [field]: value }, [action]: vi.fn(() => new Promise(done => { resolve = done; })) };
    const pending = component.methods.submit.call(ctx);
    await component.methods.submit.call(ctx);
    expect(ctx[action]).toHaveBeenCalledTimes(1);
    expect(ctx[dialog]).toBe(true);
    resolve(true);
    await pending;
    expect(ctx[dialog]).toBe(false);
    expect(ctx.form[field]).toBe('');
  });
});

describe('resource maintenance', () => {
  it('keeps the settings confirmation open after a failed prune', async () => {
    const error = new Error('daemon unavailable');
    axios.post.mockRejectedValueOnce(error);
    const ctx = { ...Prune.data(), selectedResource: { key: 'volumes' }, setMessage: vi.fn(), setErr: vi.fn() };
    await Prune.methods.prune.call(ctx, 'volumes');
    expect(ctx.selectedResource).toEqual({ key: 'volumes' });
    expect(ctx.setMessage).not.toHaveBeenCalled();
    expect(ctx.setErr).toHaveBeenCalledWith(error);
    expect(ctx.isLoading).toBe(false);
  });

  it('uses explicit daemon keys regardless of their response order', async () => {
    axios.post.mockResolvedValueOnce({ data: { SpaceReclaimed: 4096, VolumesDeleted: ['data'] } });
    const ctx = { ...Prune.data(), selectedResource: { key: 'volumes' }, setMessage: vi.fn(), setErr: vi.fn(), formatBytes: Prune.methods.formatBytes };
    await Prune.methods.prune.call(ctx, 'volumes');
    expect(ctx.setMessage).toHaveBeenCalledWith('1 volumes pruned. Space reclaimed: 4 KB.');
    expect(ctx.selectedResource).toBeNull();
  });

  it.each([
    [ImageList, imageSource, 'images', { Id: 'sha256:one', RepoTags: [], RepoDigests: null }],
    [NetworkList, networkSource, 'networks', { Id: 'net-one', Name: 'bridge' }],
    [VolumeList, volumeSource, 'volumes', { Name: 'data' }],
  ])('renders activators and row actions with nullable metadata', (component, source, module, item) => {
    const errors = [];
    const nodes = [];
    const renderer = Vue.createRenderer({
      createElement: type => { const node = { type, props: {}, children: [] }; nodes.push(node); return node; },
      createText: text => ({ text }), createComment: text => ({ text }),
      setText: (node, text) => { node.text = text; },
      setElementText: (node, text) => { node.text = text; },
      patchProp: (node, key, old, value) => { node.props[key] = value; },
      insert: (node, parent) => { parent.children.push(node); node.parent = parent; },
      remove: () => {}, parentNode: node => node.parent, nextSibling: () => null,
    });
    const tags = new Set([...source.matchAll(/<(v-[a-z-]+)/g)].map(match => match[1]));
    const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
    const app = renderer.createApp({ ...component, render });
    app.provide(Vue.ssrContextKey, { modules: new Set() });
    for (const tag of tags) {
      app.component(tag, {
        inheritAttrs: false,
        setup: (_, { attrs, slots }) => () => Vue.h(tag, attrs, [
          slots.activator?.({ props: {} }), slots.default?.(),
          ...(tag === 'v-data-table' ? ['item.Name', 'item.RepoTags', 'item.Id', 'item.Project', 'item.Driver', 'item.Created', 'item.CreatedAt']
            .map(name => slots[name]?.({ item })) : []),
        ]),
      });
    }
    app.use(createStore({ modules: { [module]: { namespaced: true, state: { [module]: [item], isLoading: false }, actions: { [`read${module[0].toUpperCase() + module.slice(1)}`]: vi.fn() } } } }));
    app.config.globalProperties.$formatDate = () => 'Today';
    app.config.errorHandler = error => errors.push(error);
    app.mount({ children: [] });
    expect(errors).toEqual([]);
    expect(nodes.some(node => node.props['aria-label']?.startsWith('Actions for'))).toBe(true);
    expect(nodes.some(node => node.props['aria-label']?.startsWith('Prune unused'))).toBe(true);
    app.unmount();
  });

  it('renders an untagged image without a RepoDigests array', () => {
    expect(ImageList.methods.handleDigests({ Id: 'sha256:0123456789abcdef', RepoDigests: null })).toBe('0123456789');
  });

  it('waits for the refreshed list before ending a prune operation', async () => {
    let resolve;
    const ctx = { ...ImageList.data(), pruneDialog: true, $store: { commit: vi.fn() }, readImages: vi.fn(() => new Promise(done => { resolve = done; })) };
    axios.post.mockResolvedValueOnce({ data: { ImagesDeleted: [{ Untagged: 'nginx' }, { Deleted: 'sha256:one' }], SpaceReclaimed: 2048 } });
    const pending = ImageList.methods.pruneImages.call(ctx);
    await vi.waitFor(() => expect(ctx.readImages).toHaveBeenCalled());
    expect(ctx.pruning).toBe(true);
    expect(ctx.$store.commit).toHaveBeenCalledWith('snackbar/setMessage', '1 images pruned. Space reclaimed: 2048 bytes.');
    resolve([]);
    await pending;
    expect(ctx.pruning).toBe(false);
  });

  it.each([[ImageList, 'Images'], [NetworkList, 'Networks'], [VolumeList, 'Volumes']])('shows prune failures as errors and retains confirmation', async (component, name) => {
    const error = new Error('Docker unavailable');
    axios.post.mockRejectedValueOnce(error);
    const ctx = { ...component.data(), pruneDialog: true, $store: { commit: vi.fn() }, [`read${name}`]: vi.fn() };
    await component.methods[`prune${name}`].call(ctx);
    expect(ctx.pruneDialog).toBe(true);
    expect(ctx.$store.commit).toHaveBeenCalledWith('snackbar/setErr', error);
    expect(ctx.pruning).toBe(false);
  });
});
