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

// Modal helpers
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

function openReceiptModal(paymentId, year, month) {
    const form = document.getElementById('receiptForm');
    form.action = `/payments/${paymentId}/edit`;
    document.getElementById('receiptModal').style.display = 'flex';
}

function openEditModal(paymentId, amount, status, paidDate) {
    const form = document.getElementById('editForm');
    form.action = `/payments/${paymentId}/edit`;
    document.getElementById('editAmount').value = amount;
    document.getElementById('editStatus').value = status;
    document.getElementById('editPaidDate').value = paidDate;
    document.getElementById('editModal').style.display = 'flex';
}

// Theme toggle
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    // Also save to backend
    fetch('/settings/theme', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({theme: next}) });
}

// Load saved theme on startup
(function() {
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    }
})();
