// Regression for BUG-007: <a target="..."> through v-html was missing
// auto-injected rel="noopener noreferrer", leaving the parent vulnerable
// to reverse-tabnabbing (popup flips window.opener.location).
//
// main.js wires enforceLinkRelNoopener into DOMPurify's
// `afterSanitizeAttributes` hook. We test the helper in isolation so the
// vitest run doesn't need a DOM or DOMPurify.
import { describe, it, expect, vi } from 'vitest';
import { enforceLinkRelNoopener } from './linkRel';

function fakeNode({ tagName = 'A', attrs = {} } = {}) {
  const store = { ...attrs };
  return {
    tagName,
    hasAttribute: (k) => k in store,
    setAttribute: vi.fn((k, v) => { store[k] = v; }),
    getAttribute: (k) => store[k],
  };
}

describe('enforceLinkRelNoopener', () => {
  it('adds rel="noopener noreferrer" when target is set on <a>', () => {
    const n = fakeNode({ attrs: { target: '_blank' } });
    enforceLinkRelNoopener(n);
    expect(n.setAttribute).toHaveBeenCalledWith('rel', 'noopener noreferrer');
  });

  it('overrides an author-supplied weak rel', () => {
    const n = fakeNode({ attrs: { target: '_blank', rel: 'author' } });
    enforceLinkRelNoopener(n);
    expect(n.setAttribute).toHaveBeenCalledWith('rel', 'noopener noreferrer');
  });

  it('also applies when target is something other than _blank', () => {
    const n = fakeNode({ attrs: { target: '_self' } });
    enforceLinkRelNoopener(n);
    expect(n.setAttribute).toHaveBeenCalledWith('rel', 'noopener noreferrer');
  });

  it('leaves <a> without target untouched', () => {
    const n = fakeNode({ attrs: { href: 'https://x' } });
    enforceLinkRelNoopener(n);
    expect(n.setAttribute).not.toHaveBeenCalled();
  });

  it('leaves non-anchor elements alone (even if they somehow have target)', () => {
    const n = fakeNode({ tagName: 'FORM', attrs: { target: '_blank' } });
    enforceLinkRelNoopener(n);
    expect(n.setAttribute).not.toHaveBeenCalled();
  });
});
