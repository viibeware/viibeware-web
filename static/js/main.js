/* ============================================================
   viibeware Corp. — Frontend JS
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

  // ── Mobile nav toggle ────────────────────────────────────
  const hamburger = document.querySelector('.nav-hamburger');
  const navLinks = document.querySelector('.nav-links');
  if (hamburger) {
    hamburger.addEventListener('click', () => {
      navLinks.classList.toggle('open');
      hamburger.classList.toggle('active');
    });
    // Close on link click
    navLinks.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        navLinks.classList.remove('open');
        hamburger.classList.remove('active');
      });
    });
  }

  // ── Nav scroll effect ────────────────────────────────────
  const nav = document.querySelector('.nav');
  let lastScroll = 0;
  window.addEventListener('scroll', () => {
    const scrollY = window.scrollY;
    nav.classList.toggle('scrolled', scrollY > 80);
    lastScroll = scrollY;
  }, { passive: true });

  // ── Active nav link tracking ─────────────────────────────
  const sections = document.querySelectorAll('[data-section]');
  const navAnchors = document.querySelectorAll('.nav-links a');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.getAttribute('data-section');
        navAnchors.forEach(a => {
          a.classList.toggle('active', a.getAttribute('href') === '#' + id);
        });
      }
    });
  }, { threshold: 0.3, rootMargin: '-70px 0px -30% 0px' });
  sections.forEach(s => observer.observe(s));

  // ── Scroll reveal ───────────────────────────────────────
  const reveals = document.querySelectorAll('.reveal');
  const revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });
  reveals.forEach(el => revealObserver.observe(el));

  // ── Install tabs ─────────────────────────────────────────
  // Each install section has its own tab bar + panels. Scope the active-class
  // toggle to the nearest <section> so tabs in one product don't collapse
  // another product's install panel.
  document.querySelectorAll('.install-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      const scope = tab.closest('section') || document;
      scope.querySelectorAll('.install-tab').forEach(t => t.classList.remove('active'));
      scope.querySelectorAll('.install-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = scope.querySelector('#' + target);
      if (panel) panel.classList.add('active');
    });
  });

  // ── Copy to clipboard ───────────────────────────────────
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const codeEl = btn.closest('.code-block').querySelector('code');
      const code = codeEl.textContent;
      navigator.clipboard.writeText(code).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.color = '#00e676';
        btn.style.borderColor = '#00e676';
        setTimeout(() => {
          btn.textContent = orig;
          btn.style.color = '';
          btn.style.borderColor = '';
        }, 2000);
      });
    });
  });

  // ── Smooth scroll for anchor links ──────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // ── Counter animation on stat cards ─────────────────────
  const statValues = document.querySelectorAll('.stat-value');
  const counterObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateValue(entry.target);
        counterObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });
  statValues.forEach(el => counterObserver.observe(el));

  function animateValue(el) {
    const text = el.dataset.value;
    const numMatch = text.match(/[\d,.]+/);
    if (!numMatch) {
      el.textContent = text;
      return;
    }
    const num = parseFloat(numMatch[0].replace(/,/g, ''));
    const prefix = text.substring(0, text.indexOf(numMatch[0]));
    const suffix = text.substring(text.indexOf(numMatch[0]) + numMatch[0].length);
    const hasDecimal = numMatch[0].includes('.');
    const decimals = hasDecimal ? numMatch[0].split('.')[1].length : 0;
    const duration = 1500;
    const start = performance.now();

    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 4);
      const current = num * ease;
      let display;
      if (hasDecimal) {
        display = current.toFixed(decimals);
      } else if (num >= 1000) {
        display = Math.floor(current).toLocaleString();
      } else {
        display = Math.floor(current).toString();
      }
      el.textContent = prefix + display + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // ── Parallax orbs on mouse move ─────────────────────────
  const hero = document.querySelector('.hero');
  if (hero) {
    const orbs = hero.querySelectorAll('.orb');
    hero.addEventListener('mousemove', e => {
      const x = (e.clientX / window.innerWidth - 0.5) * 2;
      const y = (e.clientY / window.innerHeight - 0.5) * 2;
      orbs.forEach((orb, i) => {
        const speed = (i + 1) * 8;
        orb.style.transform = `translate(${x * speed}px, ${y * speed}px)`;
      });
    });
  }

});
