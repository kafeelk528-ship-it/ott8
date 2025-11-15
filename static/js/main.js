document.addEventListener('DOMContentLoaded', () => {
  // update any cart count element if needed (server sets session cart_count)
  // simple toast hide after 4s
  setTimeout(()=> {
    document.querySelectorAll('.flash').forEach(el=> el.style.display='none')
  }, 4000);
});
