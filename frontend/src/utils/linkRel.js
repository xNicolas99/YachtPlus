// Force rel="noopener noreferrer" on <a target="..."> elements. Used as a
// DOMPurify `afterSanitizeAttributes` hook by src/main.js. Lives in its
// own no-dependency file so unit tests can import the contract without
// booting Vue + Vuetify + DOMPurify (which need a DOM).
export function enforceLinkRelNoopener(node) {
  if (node.tagName === 'A' && node.hasAttribute('target')) {
    node.setAttribute('rel', 'noopener noreferrer');
  }
}
