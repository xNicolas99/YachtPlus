import { describe, expect, it } from 'vitest';
import { localSearchResults, remoteSearchResults, searchDestination } from '@/utils/search';

describe('shared search result contract', () => {
  it('matches local names and images safely and limits each source', () => {
    const apps = [null, {}, { name: 'web', Config: { Image: 'nginx:alpine' } },
      ...Array.from({ length: 10 }, (_, index) => ({ name: `nginx-${index}` }))];
    expect(localSearchResults(apps, '  NGINX ')).toHaveLength(5);
    expect(localSearchResults(apps, 'nginx')[0]).toMatchObject({ title: 'web', id: 'web', type: 'app' });
    expect(localSearchResults(apps, 'n')).toEqual([]);
    expect(localSearchResults(null, 'nginx')).toEqual([]);
  });

  it('preserves the API full repository name for DockerHub deployment', () => {
    const results = remoteSearchResults({ dockerhub: [
      null, {}, { full_name: '' },
      { name: 'nginx', namespace: 'linuxserver', full_name: 'linuxserver/nginx' },
    ], templates: [{ id: 7, name: 'Web server' }] });
    expect(results).toHaveLength(2);
    expect(results[1]).toMatchObject({ title: 'linuxserver/nginx', id: 'linuxserver/nginx', type: 'image' });
    expect(searchDestination(results[1])).toEqual({ path: '/apps/deploy', query: { image: 'linuxserver/nginx' } });
    expect(searchDestination(results[0])).toEqual({ name: 'Deploy', params: { appId: 7 } });
  });

  it('caps template and DockerHub results independently', () => {
    const rows = Array.from({ length: 100 }, (_, id) => ({ id, title: `template-${id}`, full_name: `image-${id}` }));
    const results = remoteSearchResults({ templates: rows, dockerhub: rows });
    expect(results.filter(item => item.type === 'template')).toHaveLength(5);
    expect(results.filter(item => item.type === 'image')).toHaveLength(5);
  });

  it.each([null, [], 'error', { templates: {} }, { dockerhub: 'unavailable' }])('rejects malformed response %j', data => {
    expect(() => remoteSearchResults(data)).toThrow('Invalid search response');
  });
});
