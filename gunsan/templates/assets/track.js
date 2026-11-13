/* GA4 custom events (gtag, or dataLayer events for Google Tag Manager) for outbound actions (map, route, official info, stays, food ...).
   Links carry data-track="<event_name>" plus optional data-place / data-provider (and, in the site assistant's
   answers, data-chat-where: 'panel' | 'dock' — the floating panel or the homes' centre question card).
   GA4 enhanced measurement also records outbound clicks; these events add meaning.
   booking_click (예약하기, pipeline/booking.py): data-provider = the booking service or 'reservationurl', and
   link_lang = the hreflang of the official page it opens (another language's page, or 'ko' for the Korean one).
   affiliate_click (제휴 예약 링크, pipeline/affiliate.py, operator 2026-11-03): a stay's booking-site link through the
   affiliate network — data-provider = the booking site (yeogi, trip, myrealtrip, hotelscombined, booking, hotels,
   expedia), place_id = the stay. Register it as a key event to compare with booking_click.
   stay_booking_cta: a press of '숙박 예약하기' (the home's button, the stays list's and a stay page's link) to the
   /stays/booking/ page, whose cards' booking-site buttons are affiliate_click too (page_kind stay-booking).
   direct_booking_click (군산각 파트너, pipeline/partners.py, operator 2026-11-04): a partner stay's own homepage — its
   direct booking and inquiry, shown before the booking sites (data-provider partner, place_id = the stay).
   partner_cta: a press toward /partners/ (the panel's '문의/제휴', the footer, a badge's '?', the booking page);
   partner_contact: the inquiry mail link on /partners/.
   ado2_click (ADO2 숏폼, pipeline/ado2.py, operator 2026-11-11 meeting): 'Powered by ADO2' and the links to the ADO2
   service — link_provider ado2 (the badge), ado2-cta ('우리 가게 영상 만들기'), ado2-page (the video's ADO2 page);
   the service link carries utm_source=<this site's host>&utm_campaign=powered_by_ado2. ado2_play (site.js): a press
   of a place's video (place_id). ado2_place: a /videos/ card's name to the place page.
   share (GA4's recommended event; the 공유 pill, site.js [data-share], operator 2026-10-17; the 보내기 box and the
   panel's '군산각 공유하기', [data-shr], operator 2026-11-11): sent by site.js through window.gunsanTrack once a share
   went through — method 'web_share' (the phone's share sheet), 'copy_link', 'kakao' (KakaoTalk handed the address),
   or on the press of a link tile 'sms', 'facebook', 'x', 'band'; content_type = the page kind (place-food, guide,
   course, events, home …), item_id = the place, guide, course or event series id, a list's key, or 'site' (the
   site's own address). The shared link carries utm_source=share&utm_medium=<method> ('qr' for the box's QR code), so
   the visits it brings show as their own source / medium.
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
