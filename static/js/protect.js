// Content protection — deters casual theft, not a security guarantee
(function () {
  // Disable right-click on protected media (not video/audio — their native controls must stay intact)
  document.addEventListener('contextmenu', function (e) {
    const t = e.target;
    if (t.tagName === 'VIDEO' || t.tagName === 'AUDIO') return;
    if (t.closest('.media-wrapper') || t.closest('.artwork-media-frame') || t.tagName === 'IMG') {
      e.preventDefault();
    }
  });

  // Disable drag on images
  document.addEventListener('dragstart', function (e) {
    if (e.target.tagName === 'IMG') e.preventDefault();
  });

  // Disable Ctrl+S (save page)
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) {
      if (document.querySelector('.media-wrapper, .artwork-media-frame')) {
        e.preventDefault();
      }
    }
  });

  // CSS injection: user-select:none on all artwork images
  const style = document.createElement('style');
  style.textContent = `
    .media-wrapper img,
    .artwork-media-frame img,
    .profile-artwork-thumb img {
      user-select: none;
      -webkit-user-select: none;
      pointer-events: none;
      -webkit-touch-callout: none;
    }
    .media-overlay {
      position: absolute;
      inset: 0;
      z-index: 2;
    }
    .media-wrapper, .artwork-media-frame, .profile-artwork-thumb {
      -webkit-user-select: none;
      user-select: none;
    }
  `;
  document.head.appendChild(style);
})();
