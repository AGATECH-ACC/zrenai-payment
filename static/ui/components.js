/* Framework-independent UI helpers. All public text values are escaped.
 * Icon markup is supplied by the vendored MIT-licensed Feather library. */
(function (root) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function icon(name, label = '') {
    const item = root.feather?.icons[name];
    if (!item) return '';
    return item.toSvg({class: 'zr-icon', 'aria-hidden': label ? 'false' : 'true', ...(label ? {role: 'img', 'aria-label': escape(label)} : {})});
  }
  function brand(product = '') {
    return `<a class="brand-lockup" href="/" aria-label="众仁额度商店"><strong>众仁<span class="brand-dot" aria-hidden="true"></span></strong><span>${escape(product || "额度商店")}</span></a>`;
  }
  function metric(label, value, note) {
    return `<div class="zr-metric metric"><span>${escape(label)}</span><strong>${escape(value)}</strong><small>${escape(note)}</small></div>`;
  }
  function badge(label, tone = 'neutral') {
    const allowed = ['neutral', 'warning', 'danger', 'success'];
    return `<span class="zr-badge zr-badge--${allowed.includes(tone) ? tone : 'neutral'}">${escape(label)}</span>`;
  }
  function button(label, {action = '', variant = 'secondary', icon: iconName = '', disabled = false} = {}) {
    const allowed = ['primary', 'secondary', 'accent', 'ghost', 'danger'];
    return `<button type="button" class="zr-button zr-button--${allowed.includes(variant) ? variant : 'secondary'}" data-ui-action="${escape(action)}"${disabled ? ' disabled' : ''}>${iconName ? icon(iconName) : ''}${escape(label)}</button>`;
  }
  function hydrate(scope = document) {
    scope.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });
  }
  root.ZRUI = Object.freeze({escape, icon, brand, metric, badge, button, hydrate});
  if (typeof module !== 'undefined') module.exports = root.ZRUI;
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', () => hydrate());
})(typeof window !== 'undefined' ? window : globalThis);
