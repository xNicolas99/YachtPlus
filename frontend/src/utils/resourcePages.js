import axios from 'axios';

// Resource tables filter and paginate locally, so load every API page before
// publishing the list. A failed page must not replace it with a partial list.
export async function readResourcePages(url) {
  const items = [];
  let total;
  do {
    const { data } = await axios.get(url, { params: { offset: items.length, limit: 500 } });
    if (!Array.isArray(data?.items) || !Number.isInteger(data.total) || data.total < 0) {
      throw new Error('Invalid resource list response');
    }
    total = data.total;
    items.push(...data.items);
    if (data.items.length === 0) break;
  } while (items.length < total);
  return items;
}
