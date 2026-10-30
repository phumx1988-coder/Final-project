document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.product-gallery').forEach(function (gallery) {
    var main = gallery.querySelector('.gallery-display img');
    if (!main) return;
    gallery.querySelectorAll('.gallery-thumb[data-gallery-src]').forEach(function (button) {
      button.addEventListener('click', function () {
        var url = button.getAttribute('data-gallery-src');
        if (!url) return;
        main.src = url;
        gallery.querySelectorAll('.gallery-thumb').forEach(function (other) {
          var active = other === button;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
      });
    });
  });
});
