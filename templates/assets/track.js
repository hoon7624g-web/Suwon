/* GA4 custom events (gtag, or dataLayer events for Google Tag Manager) for outbound actions (map, route, official info, stays, food ...).
   Links carry data-track="<event_name>" plus optional data-place / data-provider (and, in the site assistant's
   answers, data-chat-where: 'panel' | 'dock' — the floating panel or the homes' centre question card).
   GA4 enhanced measurement also records outbound clicks; these events add meaning.
   booking_click (예약하기, pipeline/booking.py): data-provider = the booking service or 'reservationurl', and
   link_lang = the hreflang of the official page it opens (another language's page, or 'ko' for the Korean one).
   share (GA4's recommended event; the 공유 pill, site.js [data-share], operator 2026-10-17; the 보내기 box and the
   panel's '<지역>각 공유하기', [data-shr], 2026-11-11 on the first site): sent by site.js through window.siteTrack once
   a share went through — method 'web_share' (the phone's share sheet), 'copy_link', 'kakao' (KakaoTalk handed the
   address), or on the press of a link tile 'sms', 'facebook', 'x', 'band'; content_type = the page kind (place-food,
   guide, course, events, home …), item_id = the place, guide, course or event series id, a list's key, or 'site'
   (the site's own address). The shared link carries utm_source=share&utm_medium=<method> ('qr' for the box's QR
   code), so the visits it brings show as their own source / medium.
   related_site_click (제휴·관련 사이트, pipeline/related_sites.py): a press on the footer strip or the home's cards —
   link_provider = the site's name.
   partner_cta (파트너 되기, pipeline/partners.py): a press toward /partners/ or its inquiry form (the panel's '문의/제휴',
   the footer, the page's buttons); partner_contact: the inquiry mail link.
   Register place_id / link_provider / page_kind / chat_where / link_lang / method / content_type / item_id as custom
   dimensions in GA4 to report on them. */
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
  window.siteTrack = send;
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
