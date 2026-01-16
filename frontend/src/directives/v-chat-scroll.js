export default {
  mounted(el, binding) {
    const config = binding.value || {};
    // Scroll to bottom on load
    scrollToBottom(el, config.smooth);

    // Observer to scroll on new content
    const observer = new MutationObserver(() => {
      // Logic to check if user is scrolled up could be added here
      scrollToBottom(el, config.smooth);
    });

    observer.observe(el, { childList: true, subtree: true, characterData: true });
    el._chatScrollObserver = observer;
  },
  unmounted(el) {
    if (el._chatScrollObserver) {
      el._chatScrollObserver.disconnect();
    }
  }
};

function scrollToBottom(el, smooth) {
  el.scrollTo({
    top: el.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto'
  });
}
