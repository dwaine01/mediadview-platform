/**
 * MediAd View — mini i18n (EN / ES) — shared across public pages.
 *
 * Usage in HTML:
 *   <span data-i18n="landing.hero.title">Fallback English text here</span>
 *   <a href="/" data-i18n="nav.home">Home</a>
 *   <input data-i18n-placeholder="form.email" placeholder="Email">
 *   <button data-i18n-html="cta.publish">Publish</button>   // innerHTML variant
 *
 * A <button id="lang-toggle"> anywhere is auto-wired to toggle ES/EN.
 * The chosen language is persisted in localStorage under 'mv_lang'.
 * On first visit the browser language is auto-detected (es-* -> es, else en).
 */
(function(){
  var DICT = {
    en: {
      "nav.home": "Home",
      "nav.about": "About",
      "nav.services": "Services",
      "nav.menus": "Digital Menus",
      "nav.contact": "Contact",
      "nav.publish": "Publish your ad here",
      "nav.dashboard": "Dashboard Login",
      "landing.badge": "Specialists in Window & Indoor Displays",
      "landing.h1a": "Your Storefront Window Is Your",
      "landing.h1b": "Best Billboard",
      "landing.p": "We install high-brightness LED displays on storefront windows, churches, and outdoor walls. Attract customers 24/7 with eye-catching digital content — managed from our cloud platform.",
      "landing.card.title": "Publish your own ad — today",
      "landing.card.sub": "Advertise on LED screens for 1, 3, 6 or 12 months · Multiple cities and locations",
      "landing.card.cta1": "Publish your ad here",
      "landing.card.cta2": "Business inquiry",
      "about.badge": "Meet The Founder",
      "about.role": "CEO & Founder — MediAd View LLC",
      "about.p1": "MediAd View is a digital display company offering professional LED solutions for indoor, outdoor, and storefront window applications.",
      "about.p2": "With installations nationwide, our displays are designed for high ambient light environments — with brightness levels up to 5,500 nits for direct sunlight visibility.",
      "about.p3": "We provide end-to-end solutions: hardware, installation, cloud management, and ongoing support.",
      "lang.toggle": "ES"
    },
    es: {
      "nav.home": "Inicio",
      "nav.about": "Nosotros",
      "nav.services": "Servicios",
      "nav.menus": "Menús Digitales",
      "nav.contact": "Contacto",
      "nav.publish": "Publica tu anuncio aquí",
      "nav.dashboard": "Ingresar",
      "landing.badge": "Especialistas en pantallas para vidrieras e interiores",
      "landing.h1a": "Tu vidriera es tu",
      "landing.h1b": "mejor cartel",
      "landing.p": "Instalamos pantallas LED de alto brillo en vidrieras, iglesias y paredes exteriores. Atrae clientes 24/7 con contenido llamativo — todo administrado desde nuestra plataforma en la nube.",
      "landing.card.title": "Publica tu anuncio tú mismo — hoy",
      "landing.card.sub": "Anúnciate en pantallas LED por 1, 3, 6 o 12 meses · Múltiples ciudades y localidades",
      "landing.card.cta1": "Publica tu anuncio aquí",
      "landing.card.cta2": "Consulta comercial",
      "about.badge": "Conoce al fundador",
      "about.role": "CEO y Fundador — MediAd View LLC",
      "about.p1": "MediAd View es una empresa de pantallas digitales que ofrece soluciones LED profesionales para interiores, exteriores y vidrieras comerciales.",
      "about.p2": "Con instalaciones a nivel nacional, nuestras pantallas están diseñadas para ambientes de alta luminosidad — con brillo de hasta 5.500 nits, visibles bajo luz solar directa.",
      "about.p3": "Ofrecemos soluciones integrales: hardware, instalación, gestión en la nube y soporte continuo.",
      "lang.toggle": "EN"
    }
  };

  function detect(){
    try {
      var saved = localStorage.getItem('mv_lang');
      if (saved === 'en' || saved === 'es') return saved;
    } catch(e){}
    var nav = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    return nav.indexOf('es') === 0 ? 'es' : 'en';
  }

  function apply(lang){
    if (!DICT[lang]) lang = 'en';
    var d = DICT[lang];
    document.documentElement.setAttribute('lang', lang);
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k = el.getAttribute('data-i18n');
      if (d[k] != null) el.textContent = d[k];
    });
    document.querySelectorAll('[data-i18n-html]').forEach(function(el){
      var k = el.getAttribute('data-i18n-html');
      if (d[k] != null) el.innerHTML = d[k];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el){
      var k = el.getAttribute('data-i18n-placeholder');
      if (d[k] != null) el.setAttribute('placeholder', d[k]);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el){
      var k = el.getAttribute('data-i18n-title');
      if (d[k] != null) el.setAttribute('title', d[k]);
    });
    // Toggle button label reflects the OTHER language you would switch to.
    var tog = document.getElementById('lang-toggle');
    if (tog) tog.textContent = d['lang.toggle'];
    try { localStorage.setItem('mv_lang', lang); } catch(e){}
    window.__mv_lang = lang;
  }

  function toggle(){
    apply(window.__mv_lang === 'es' ? 'en' : 'es');
  }

  function boot(){
    apply(detect());
    var tog = document.getElementById('lang-toggle');
    if (tog && !tog.__mv_wired) {
      tog.addEventListener('click', function(e){ e.preventDefault(); toggle(); });
      tog.__mv_wired = true;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  // Expose for pages that render content dynamically after boot.
  window.MV_I18N = { apply: apply, toggle: toggle, detect: detect };
})();
