import { describe, expect, it, vi } from 'vitest';
import {
  CONTAINER_VIEW_VERSION, DEFAULT_CONTAINER_COLUMNS, NO_STACK,
  normalizeContainerView, normalizeContainerPreferences, containerViewStorageKey,
  readContainerPreferences, writeContainerPreferences, containerViewFromQuery,
  containerViewQuery, hasContainerViewQuery, containerHealth, filterContainers,
} from './containerViews';

const container = (name, state, options = {}) => ({
  Id: `id-${name}`, name, State: { Status: state, ...options.state },
  Config: { Image: options.image || 'nginx:alpine', Labels: { 'com.docker.compose.project': options.stack || '' }, Env: ['PASSWORD=private-value'] },
  ...(options.update ? { isUpdatable: true } : {}),
});
const inventory = [
  container('web', 'running', { stack: 'production', state: { Health: { Status: 'unhealthy' } }, update: true }),
  container('database', 'running', { stack: 'production', state: { Health: { Status: 'healthy' } }, image: 'postgres:16' }),
  container('cache', 'exited', { stack: 'testing' }),
  container('dead', 'dead'),
  container('new', 'created'),
];

describe('container inventory filters', () => {
  it('combines health, state, stack and update availability from actual inspection data', () => {
    expect(filterContainers(inventory, { status: 'running', health: 'unhealthy', stack: 'production', updates: 'available' }).map(item => item.name)).toEqual(['web']);
    expect(filterContainers(inventory, { status: 'running', health: 'healthy', updates: 'available' })).toEqual([]);
    expect(filterContainers(inventory, { status: 'running', health: 'healthy', updates: 'unconfirmed' }).map(item => item.name)).toEqual(['database']);
  });

  it('matches the dashboard stopped count without treating created or paused containers as stopped', () => {
    expect(filterContainers(inventory, { status: 'stopped' }).map(item => item.name)).toEqual(['cache', 'dead']);
    expect(filterContainers(inventory, { status: 'created' }).map(item => item.name)).toEqual(['new']);
  });

  it('handles Docker summary health and labels as well as inspection responses', () => {
    const summary = { name: 'summary', State: 'running', Status: 'Up 2 minutes (health: starting)', Labels: { 'com.docker.compose.project': 'testing' } };
    expect(containerHealth(summary)).toBe('starting');
    expect(filterContainers([summary], { status: 'running', health: 'starting', stack: 'testing' })).toEqual([summary]);
    expect(containerHealth({ Status: 'Up 2 minutes (unhealthy)' })).toBe('unhealthy');
    expect(containerHealth({ Status: 'Up 2 minutes (healthy)' })).toBe('healthy');
  });

  it('identifies containers without stacks or health checks, including incomplete metadata', () => {
    expect(filterContainers(inventory, { stack: NO_STACK, health: 'none' }).map(item => item.name)).toEqual(['dead', 'new']);
    expect(filterContainers([{}], { health: 'none', stack: NO_STACK })).toEqual([{}]);
    expect(filterContainers(null, {})).toEqual([]);
  });

  it('searches visible identifiers, image and state without inspecting environment secrets', () => {
    expect(filterContainers(inventory, { search: 'POSTGRES' }).map(item => item.name)).toEqual(['database']);
    expect(filterContainers(inventory, { search: 'testing' }).map(item => item.name)).toEqual(['cache']);
    expect(filterContainers(inventory, { search: 'private-value' })).toEqual([]);
  });

  it('accepts confirmed updates from the existing store without mutating inventory', () => {
    const before = structuredClone(inventory);
    expect(filterContainers(inventory, { updates: 'available' }, ['database']).map(item => item.name)).toEqual(['web', 'database']);
    expect(inventory).toEqual(before);
  });
});

describe('bounded container-view preferences', () => {
  it('retains only supported column IDs and requires the name column', () => {
    expect(normalizeContainerView({ columns: ['image', 'image', { key: 'password' }, 'secret'] }).columns).toEqual(['name', 'image']);
    expect(normalizeContainerView({ columns: [] }).columns).toEqual(['name']);
    expect(normalizeContainerView().columns).toEqual(DEFAULT_CONTAINER_COLUMNS);
  });

  it('bounds text and drops invalid filters and arbitrary input fields', () => {
    const normalized = normalizeContainerView({ status: 'malicious', health: ['unhealthy'], updates: 'current', search: 'x'.repeat(500), stack: 'a'.repeat(1000), password: 'secret' });
    expect(normalized.status).toBe('');
    expect(normalized.health).toBe('');
    expect(normalized.updates).toBe('');
    expect(normalized.search).toHaveLength(128);
    expect(normalized.stack).toHaveLength(264);
    expect(normalized).not.toHaveProperty('password');
    expect(normalizeContainerView(null)).toEqual(normalizeContainerView());
  });

  it('ignores unsupported versions and isolates preferences by account', () => {
    expect(normalizeContainerPreferences({ version: 99, current: { search: 'old' } }).current.search).toBe('');
    expect(containerViewStorageKey('alice')).not.toBe(containerViewStorageKey('bob'));
    expect(containerViewStorageKey('a/b')).toContain('a%2Fb');
  });

  it('rejects malformed storage and survives browser storage restrictions', () => {
    expect(readContainerPreferences({ getItem: () => '{bad json' }, 'key')).toEqual(normalizeContainerPreferences());
    expect(readContainerPreferences({ getItem() { throw new Error('Blocked'); } }, 'key')).toEqual(normalizeContainerPreferences());
    expect(readContainerPreferences({ getItem: () => 'x'.repeat(65537) }, 'key')).toEqual(normalizeContainerPreferences());
    expect(writeContainerPreferences({ setItem() { throw new Error('Quota exceeded'); } }, 'key', {})).toBe(false);
    expect(writeContainerPreferences(null, 'key', {})).toBe(false);
  });

  it('writes only configuration primitives, never Docker objects or injected credentials', () => {
    const storage = { setItem: vi.fn() };
    const view = { name: 'Production', config: { status: 'running', columns: ['name'], Env: inventory[0].Config.Env } };
    expect(writeContainerPreferences(storage, 'key', { version: CONTAINER_VIEW_VERSION, current: { stack: 'production', password: 'sentinel-secret' }, savedViews: [view], containers: inventory })).toBe(true);
    const stored = JSON.parse(storage.setItem.mock.calls[0][1]);
    expect(stored.current.stack).toBe('production');
    expect(stored.savedViews[0].config.status).toBe('running');
    expect(JSON.stringify(stored)).not.toMatch(/sentinel-secret|PASSWORD|private-value|Config|Env/);
  });

  it('deduplicates saved names, caps their number and drops invalid selection', () => {
    const savedViews = [{ name: ' Production ' }, { name: 'production' }, { name: '' }, ...Array.from({ length: 30 }, (_, i) => ({ name: `View ${i}` }))];
    const normalized = normalizeContainerPreferences({ version: 1, savedViews, selectedView: 'missing' });
    expect(normalized.savedViews).toHaveLength(20);
    expect(normalized.savedViews[0].name).toBe('Production');
    expect(normalized.selectedView).toBe('');
  });
});

describe('dashboard and URL filter contract', () => {
  it('applies dashboard query filters while preserving column choices', () => {
    const view = containerViewFromQuery({ status: 'running', health: 'unhealthy', q: 'web' }, ['name', 'project']);
    expect(view).toMatchObject({ status: 'running', health: 'unhealthy', search: 'web', columns: ['name', 'project'] });
    expect(hasContainerViewQuery({ health: 'unhealthy' })).toBe(true);
    expect(hasContainerViewQuery({ image: 'nginx' })).toBe(false);
  });

  it('rejects duplicated/malformed query filters and clears previous filters in generated addresses', () => {
    expect(containerViewFromQuery({ status: ['running', 'dead'], health: 'invalid', stack: ['testing'], q: {} }).status).toBe('');
    expect(containerViewQuery({ health: 'unhealthy' }, { status: 'stopped', stack: 'old', page: '2' })).toEqual({ page: '2', health: 'unhealthy' });
    expect(containerViewFromQuery({}, ['name']).search).toBe('');
  });
});
