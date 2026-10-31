/* GA4 custom events (gtag, or dataLayer events for Google Tag Manager) for outbound actions (map, route, official info, stays, food ...).
   Links carry data-track="<event_name>" plus optional data-place / data-provider (and, in the site assistant's
   answers, data-chat-where: 'panel' | 'dock' — the floating panel or the homes' centre question card).
   GA4 enhanced measurement also records outbound clicks; these events add meaning.
   booking_click (예약하기, pipeline/booking.py): data-provider = the booking service or 'reservationurl', and
   link_lang = the hreflang of the official page it opens (another language's page, or 'ko' for the Korean one).
   share (GA4's recommended event; the local bar's 공유, site.js [data-share], operator 2026-10-17): sent by site.js
   through window.gunsanTrack once a share went through — method 'web_share' (the phone's share sheet) or
   'copy_link', content_type = the page kind (place-food, guide, course, events …), item_id = the place, guide,
   course or event series id. The shared link carries utm_source=share&utm_medium=<method>, so the visits it
   brings show as their own source / medium.
   chat_answer (chat.js): how each assistant answer ended, never its words — outcome answered | no_links | cut | stopped
   | error, error_code, links (site pages linked), answer_lang ('und' when unsure), part (first, or more for the rest
   of a cut answer — count answers on part = first), not_on_site (a Korean answer saying 사이트에 없음).
   Register place_id / link_provider / page_kind / chat_where / link_lang / method / content_type / item_id / outcome /
   error_code / answer_lang / part / not_on_site as custom dimensions (links as a custom metric) in GA4 to report on them. */
(function () {
  function send(name, params) {
    if (typeof window.gtag === 'function') { window.gtag('event', name, params); return; }
    // Google Tag Manager: the same event as a dataLayer push (a GTM trigger on event = name sends it to GA4)
    if (window.dataLayer && window.dataLayer.push) {
      var ev = { event: name };
      for (var k in params) ev[k] = params[k];
      window.dataLayer.push(ev);
    }
  }
  window.gunsanTrack = send;
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[data-track]') : null;
    if (!a) return;
    var params = {
      link_url: a.href,
      place_id: a.getAttribute('data-place') || '',
      link_provider: a.getAttribute('data-provider') || '',
      page_kind: document.body.getAttribute('data-page-kind') || ''
    };
    if (a.hasAttribute('data-chat-where')) params.chat_where = a.getAttribute('data-chat-where');
    if (a.hasAttribute('hreflang')) params.link_lang = a.getAttribute('hreflang');
    send(a.getAttribute('data-track'), params);
  }, true);
})();
