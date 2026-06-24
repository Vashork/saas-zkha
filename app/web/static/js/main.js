/* === Main JS === */

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('[id$="Modal"]');
        modals.forEach(m => m.style.display = 'none');
        const forms = document.querySelectorAll('[id$="Form"]');
        forms.forEach(f => f.style.display = 'none');
    }
});

// Close modal on outside click
document.addEventListener('click', (e) => {
    const modals = document.querySelectorAll('[id$="Modal"]');
    modals.forEach(m => {
        if (m.style.display === 'flex' && e.target === m) {
            m.style.display = 'none';
        }
    });
});
