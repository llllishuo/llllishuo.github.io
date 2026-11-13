/* Menghan Studio — 站点交互：主题切换 / 移动导航 / 文章筛选 / 代码复制 / 目录高亮 */
(function () {
  'use strict';

  var root = document.documentElement;

  /* ---------- 主题 ---------- */
  var toggle = document.getElementById('theme-toggle');
  function setTheme(name, persist) {
    root.setAttribute('data-theme', name);
    if (persist) {
      try { localStorage.setItem('ms-theme', name); } catch (e) { /* 隐私模式 */ }
    }
    if (toggle) {
      toggle.setAttribute('aria-pressed', name === 'dark' ? 'true' : 'false');
    }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) { meta.setAttribute('content', name === 'dark' ? '#131211' : '#f7f4ee'); }
  }
  if (toggle) {
    setTheme(root.getAttribute('data-theme') || 'light', false);
    toggle.addEventListener('click', function () {
      setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark', true);
    });
  }

  /* ---------- 移动端导航 ---------- */
  var menuBtn = document.getElementById('menu-toggle');
  var nav = document.getElementById('site-nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('is-open');
        menuBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- 文章筛选 ---------- */
  var input = document.getElementById('post-filter');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.filter-chip'));
  var rows = Array.prototype.slice.call(document.querySelectorAll('.post-row'));
  var empty = document.getElementById('filter-empty');
  var activeCat = 'all';

  function applyFilter() {
    var q = (input ? input.value : '').trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (row) {
      var okCat = activeCat === 'all' || row.getAttribute('data-cat') === activeCat;
      var hay = row.getAttribute('data-search') || '';
      var title = row.querySelector('h3');
      if (title) { hay += ' ' + title.textContent.toLowerCase(); }
      var okText = !q || hay.indexOf(q) !== -1;
      var vis = okCat && okText;
      row.hidden = !vis;
      if (vis) { shown++; }
    });
    // 空年份块一起隐藏
    Array.prototype.forEach.call(document.querySelectorAll('.year-block'), function (block) {
      var any = block.querySelectorAll('.post-row:not([hidden])').length > 0;
      block.hidden = !any;
    });
    if (empty) { empty.hidden = shown !== 0; }
  }

  if (rows.length) {
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        activeCat = chip.getAttribute('data-cat') || 'all';
        chips.forEach(function (c) { c.classList.toggle('is-active', c === chip); });
        applyFilter();
      });
    });
    if (input) { input.addEventListener('input', applyFilter); }
  }

  /* ---------- 代码块复制 ---------- */
  var COPY_LABEL = '复制';
  Array.prototype.forEach.call(document.querySelectorAll('.codehilite, .prose pre'), function (block) {
    if (block.querySelector('.copy-btn')) { return; }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = COPY_LABEL;
    btn.addEventListener('click', function () {
      var code = block.querySelector('code');
      var text = code ? code.innerText : block.innerText;
      var done = function () {
        btn.textContent = '已复制';
        btn.classList.add('done');
        setTimeout(function () {
          btn.textContent = COPY_LABEL;
          btn.classList.remove('done');
        }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { /* 忽略 */ });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* 忽略 */ }
        document.body.removeChild(ta);
      }
    });
    block.appendChild(btn);
  });

  /* ---------- 目录滚动高亮 ---------- */
  var toc = document.querySelector('.post-toc');
  if (toc && 'IntersectionObserver' in window) {
    var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
    var map = {};
    links.forEach(function (a) {
      var id = decodeURIComponent(a.getAttribute('href').slice(1));
      map[id] = a;
    });
    var heads = Array.prototype.filter.call(
      document.querySelectorAll('.prose h2[id], .prose h3[id]'),
      function (h) { return map[h.id]; }
    );
    var current = null;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) { return; }
        var a = map[en.target.id];
        if (!a || a === current) { return; }
        if (current) { current.style.borderLeftColor = ''; current.style.color = ''; }
        a.style.borderLeftColor = 'var(--accent)';
        a.style.color = 'var(--accent)';
        current = a;
      });
    }, { rootMargin: '-72px 0px -70% 0px', threshold: 0 });
    heads.forEach(function (h) { obs.observe(h); });
  }
}());
