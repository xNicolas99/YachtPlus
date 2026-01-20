const VueChatScroll = {
    install: (app) => {
        app.directive('chat-scroll', {
            mounted(el) {
                el.scrollTop = el.scrollHeight;
                // Observer to scroll on content change
                const observer = new MutationObserver(() => {
                    el.scrollTop = el.scrollHeight;
                });
                observer.observe(el, { childList: true, subtree: true });
                el._chatScrollObserver = observer;
            },
            unmounted(el) {
                if (el._chatScrollObserver) {
                    el._chatScrollObserver.disconnect();
                }
            }
        });
    }
};
export default VueChatScroll;
