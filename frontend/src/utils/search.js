export const SEARCH_DELAY_MS = 300;
export const SEARCH_TIMEOUT_MS = 10000;

// Both search entry points use the same bounded, safe result shape.
export function localSearchResults(apps, query) {
  const term = query.trim().toLowerCase();
  if (term.length < 2 || !Array.isArray(apps)) return [];
  return apps.filter(app => typeof app?.name === 'string' && (
    app.name.toLowerCase().includes(term) || String(app.Config?.Image || '').toLowerCase().includes(term)
  )).slice(0, 5).map(app => ({
    key: `app:${app.name}`, type: 'app', id: app.name,
    title: app.name, description: app.Config?.Image || '', source: 'Apps',
  }));
}

export function remoteSearchResults(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data) ||
      (data.templates != null && !Array.isArray(data.templates)) ||
      (data.dockerhub != null && !Array.isArray(data.dockerhub))) {
    throw new Error('Invalid search response');
  }
  const templates = (data.templates || []).filter(item =>
    item && item.id != null && typeof (item.title || item.name) === 'string'
  ).slice(0, 5).map(item => ({
    key: `template:${item.id}`, type: 'template', id: item.id,
    title: item.title || item.name, description: item.description || '', source: 'Templates',
  }));
  const images = (data.dockerhub || []).filter(item =>
    typeof item?.full_name === 'string' && item.full_name.trim()
  ).slice(0, 5).map(item => ({
    key: `image:${item.full_name}`, type: 'image', id: item.full_name,
    title: item.full_name, description: item.description || '', source: 'DockerHub',
  }));
  return [...templates, ...images];
}

export function searchDestination(item) {
  if (item.type === 'app') return { path: `/apps/${encodeURIComponent(item.id)}/info` };
  if (item.type === 'template') return { name: 'Deploy', params: { appId: item.id } };
  if (item.type === 'image') return { path: '/apps/deploy', query: { image: item.id } };
}
