export const CONTAINER_VIEW_VERSION = 1;
export const MAX_SAVED_CONTAINER_VIEWS = 20;
export const CONTAINER_COLUMNS = ['name', 'project', 'status', 'health', 'image', 'ports', 'created'];
export const DEFAULT_CONTAINER_COLUMNS = ['name', 'status', 'health', 'image', 'ports', 'created'];
const STATUSES = ['', 'running', 'stopped', 'paused', 'restarting', 'created', 'dead'];
const HEALTH = ['', 'healthy', 'unhealthy', 'starting', 'none'];
const UPDATES = ['', 'available', 'unconfirmed'];
const FILTER_QUERY_KEYS = ['status', 'health', 'stack', 'updates', 'q'];
export const NO_STACK = '__none__';

const text = (value, maximum) => typeof value === 'string' ? value.slice(0, maximum) : '';
const choice = (value, choices) => choices.includes(value) ? value : '';

export function normalizeContainerView(value = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) value = {};
  const columns = Array.isArray(value.columns)
    ? [...new Set(value.columns.filter(column => CONTAINER_COLUMNS.includes(column)))]
    : [...DEFAULT_CONTAINER_COLUMNS];
  if (!columns.includes('name')) columns.unshift('name');
  return {
    search: text(value.search, 128),
    status: choice(value.status, STATUSES),
    health: choice(value.health, HEALTH),
    stack: text(value.stack, 264),
    updates: choice(value.updates, UPDATES),
    columns,
  };
}

export function normalizeContainerPreferences(value = {}) {
  if (!value || value.version !== CONTAINER_VIEW_VERSION) value = {};
  const names = new Set();
  const savedViews = (Array.isArray(value.savedViews) ? value.savedViews : [])
    .filter(view => {
      const name = text(view?.name, 60).trim();
      if (!name || names.has(name.toLowerCase()) || names.size >= MAX_SAVED_CONTAINER_VIEWS) return false;
      names.add(name.toLowerCase());
      return true;
    })
    .map(view => ({ name: text(view.name, 60).trim(), config: normalizeContainerView(view.config) }));
  const selectedView = savedViews.some(view => view.name === value.selectedView) ? value.selectedView : '';
  return {
    version: CONTAINER_VIEW_VERSION,
    current: normalizeContainerView(value.current),
    savedViews,
    selectedView,
  };
}

export function containerViewStorageKey(username = '') {
  return `yachtplus.container-views.v${CONTAINER_VIEW_VERSION}:${encodeURIComponent(text(username, 264) || 'development')}`;
}

export function readContainerPreferences(storage, key) {
  try {
    const raw = storage?.getItem(key);
    if (raw && raw.length > 65536) return normalizeContainerPreferences();
    return normalizeContainerPreferences(raw ? JSON.parse(raw) : undefined);
  } catch {
    return normalizeContainerPreferences();
  }
}

export function writeContainerPreferences(storage, key, value) {
  try {
    if (!storage) return false;
    // Persist only bounded filters, column identifiers and view names, never
    // Docker inspection objects, environment values or credentials.
    storage.setItem(key, JSON.stringify(normalizeContainerPreferences(value)));
    return true;
  } catch {
    return false;
  }
}

export function hasContainerViewQuery(query = {}) {
  return FILTER_QUERY_KEYS.some(key => Object.hasOwn(query, key));
}

export function containerViewFromQuery(query = {}, columns) {
  return normalizeContainerView({
    status: query.status, health: query.health, stack: query.stack,
    updates: query.updates, search: query.q, columns,
  });
}

export function containerViewQuery(view, query = {}) {
  const next = { ...query };
  FILTER_QUERY_KEYS.forEach(key => { delete next[key]; });
  const config = normalizeContainerView(view);
  for (const key of ['status', 'health', 'stack', 'updates']) {
    if (config[key]) next[key] = config[key];
  }
  if (config.search) next.q = config.search;
  return next;
}

export function containerStatus(container) {
  return String(typeof container?.State === 'string' ? container.State : container?.State?.Status || '').toLowerCase();
}

export function containerHealth(container) {
  const status = container?.State?.Health?.Status;
  if (typeof status === 'string') return status.toLowerCase();
  const summary = container?.Status || '';
  if (typeof summary === 'string') {
    if (summary.includes('(unhealthy)')) return 'unhealthy';
    if (summary.includes('(healthy)')) return 'healthy';
    if (summary.includes('(health: starting)')) return 'starting';
  }
  return 'none';
}

export function containerStack(container) {
  return container?.Config?.Labels?.['com.docker.compose.project'] || container?.Labels?.['com.docker.compose.project'] || '';
}

export function filterContainers(containers, view, knownUpdates = []) {
  const config = normalizeContainerView(view);
  const updates = new Set(Array.isArray(knownUpdates) ? knownUpdates.filter(item => typeof item === 'string') : []);
  const term = config.search.trim().toLowerCase();
  return (Array.isArray(containers) ? containers : []).filter(container => {
    const status = containerStatus(container);
    const stack = containerStack(container);
    const name = String(container?.name || container?.Name || '').replace(/^\//, '');
    const update = container?.isUpdatable === true || updates.has(name) || updates.has(container?.Id);
    if (config.status === 'stopped' ? !['stopped', 'exited', 'dead'].includes(status) : config.status && config.status !== status) return false;
    if (config.health && containerHealth(container) !== config.health) return false;
    if (config.stack && (config.stack === NO_STACK ? !!stack : config.stack !== stack)) return false;
    if (config.updates === 'available' && !update) return false;
    if (config.updates === 'unconfirmed' && update) return false;
    if (term) {
      const haystack = [name, container?.Config?.Image || container?.Image, stack, status, containerHealth(container)].join(' ').toLowerCase();
      if (!haystack.includes(term)) return false;
    }
    return true;
  });
}
