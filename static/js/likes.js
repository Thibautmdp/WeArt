// AJAX like buttons — attach to all .like-btn on page load
function attachLike(btn) {
  if (btn.dataset.likeAttached) return;
  btn.dataset.likeAttached = '1';
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const artworkId = btn.dataset.artworkId;
    if (!artworkId) return;
    try {
      const resp = await fetch(`/api/like/${artworkId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (resp.status === 401) {
        window.location.href = '/login';
        return;
      }
      if (resp.ok) {
        const data = await resp.json();
        const countEl = btn.querySelector('.like-count');
        const heartEl = btn.querySelector('.heart');
        if (countEl) countEl.textContent = data.count;
        if (heartEl) heartEl.textContent = data.liked ? '❤️' : '🤍';
        btn.classList.toggle('liked', data.liked);
      }
    } catch (err) {
      console.error('Like error:', err);
    }
  });
}

document.querySelectorAll('.like-btn').forEach(attachLike);
