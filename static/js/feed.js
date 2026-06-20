// Infinite scroll feed using Intersection Observer
(function () {
  let currentPage = 2;
  let loading = false;
  let hasMore = true;

  const grid = document.getElementById('feed-grid');
  const sentinel = document.getElementById('scroll-sentinel');
  const loadingEl = document.getElementById('loading-more');

  if (!grid || !sentinel) return;

  // Read active filter from URL
  const params = new URLSearchParams(window.location.search);
  const activeType = params.get('type') || 'all';

  function buildCard(a) {
    const mediaHtml = buildMedia(a);
    return `
<div class="artwork-card" onclick="window.location='${a.url}'">
  ${a.is_ai_generated ? '<span class="ai-badge">✨IA</span>' : ''}
  ${a.is_for_sale ? `<span class="sale-badge">${a.price ? Math.round(a.price) + ' €' : 'À vendre'}</span>` : ''}
  <div class="media-wrapper">${mediaHtml}<div class="media-overlay"></div></div>
  <div class="card-body">
    <div class="card-meta"><span class="media-type-badge">${a.media_label}</span></div>
    <div class="card-title">${escHtml(a.title)}</div>
    <div class="card-artist">par <a href="/artist/${a.artist_username}" onclick="event.stopPropagation()">${escHtml(a.artist)}</a></div>
    <div class="card-actions">
      <button class="like-btn" data-artwork-id="${a.id}" onclick="event.stopPropagation()">
        <span class="heart">🤍</span> <span class="like-count">${a.like_count}</span>
      </button>
    </div>
  </div>
</div>`;
  }

  function buildMedia(a) {
    if (a.is_image) {
      const subfolder = a.display_path && a.display_path.startsWith('wm_') ? 'watermarked' : 'thumbnails';
      const file = subfolder === 'watermarked' ? a.display_path : (a.thumbnail_path || a.display_path);
      if (!file) return '<div style="height:200px;display:flex;align-items:center;justify-content:center;color:#555">🎨</div>';
      return `<img src="/media/${subfolder}/${a.token}/${file}" alt="${escHtml(a.title)}" loading="lazy">`;
    }
    if (a.is_audio) {
      return `<div class="audio-placeholder"><span>🎵</span><div class="title">${escHtml(a.title)}</div></div>`;
    }
    if (a.is_video) {
      return `<div style="height:180px;display:flex;align-items:center;justify-content:center;background:#0d0d0d;color:#555">▶️</div>`;
    }
    return '<div style="height:180px;display:flex;align-items:center;justify-content:center;color:#555">🎨</div>';
  }

  function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  async function loadNextPage() {
    if (loading || !hasMore) return;
    loading = true;
    if (loadingEl) loadingEl.style.display = 'flex';

    try {
      const resp = await fetch(`/api/feed?page=${currentPage}&type=${activeType}`);
      const data = await resp.json();

      data.artworks.forEach(a => {
        const div = document.createElement('div');
        div.innerHTML = buildCard(a);
        const card = div.firstElementChild;
        grid.appendChild(card);
        // attach like handler
        const likeBtn = card.querySelector('.like-btn');
        if (likeBtn) attachLike(likeBtn);
        // protect
        const overlay = card.querySelector('.media-overlay');
        if (overlay) overlay.addEventListener('contextmenu', e => e.preventDefault());
      });

      hasMore = data.has_more;
      currentPage = data.next_page;
    } catch (e) {
      console.error('Feed load error:', e);
    } finally {
      loading = false;
      if (loadingEl) loadingEl.style.display = hasMore ? 'none' : 'none';
    }
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) loadNextPage();
  }, { rootMargin: '300px' });

  observer.observe(sentinel);
})();
