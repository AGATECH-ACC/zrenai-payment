/* Application behaviors only; authentication and mutations stay server-side. */
(() => {
  'use strict';
  let toastTimer;
  window.ZrenUI = Object.freeze({
    notify(message) {
      const toast = document.getElementById('ui-notification');
      if (!toast) return;
      clearTimeout(toastTimer);
      toast.textContent = message;
      toast.hidden = false;
      toastTimer = setTimeout(() => { toast.hidden = true; }, 6000);
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-open-dialog]').forEach(button => {
      const dialog = document.getElementById(button.dataset.openDialog);
      if (!dialog) return;
      button.addEventListener('click', () => {
        dialog.showModal();
        dialog.addEventListener('close', () => button.focus(), {once: true});
      });
    });
    document.querySelectorAll('[data-close-dialog]').forEach(button => {
      button.addEventListener('click', () => button.closest('dialog').close());
    });
    document.querySelectorAll('[data-dismiss-message]').forEach(button => {
      button.addEventListener('click', () => button.closest('.app-message').remove());
    });
  });
})();
