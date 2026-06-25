/* === Main JS === */

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('[id$="Modal"]');
        modals.forEach(m => m.style.display = 'none');
        const legacyAddForm = document.getElementById('addForm');
        if (legacyAddForm && legacyAddForm.classList.contains('card-custom')) {
            legacyAddForm.style.display = 'none';
        }
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
    const item = document.getElementById(id);
    if (item) item.style.display = 'none';
}

function openReceiptModal(paymentId, year, month) {
    const form = document.getElementById('receiptForm');
    if (!form) return;
    form.action = `/payments/${paymentId}/edit`;
    document.getElementById('receiptModal').style.display = 'flex';
}

function openEditModal(paymentId, amount, status, paidDate) {
    const form = document.getElementById('editForm');
    if (!form) return;
    form.action = `/payments/${paymentId}/edit`;
    document.getElementById('editAmount').value = amount || '';
    document.getElementById('editStatus').value = status || 'pending';
    document.getElementById('editPaidDate').value = paidDate || '';
    if (typeof toggleEditPaidFields === 'function') toggleEditPaidFields();
    document.getElementById('editModal').style.display = 'flex';
}

function showAddPaymentForm() {
    const modal = document.getElementById('addPaymentModal');
    if (modal) {
        if (typeof openAddPaymentModal === 'function') {
            return openAddPaymentModal();
        }
        modal.style.display = 'flex';
        return false;
    }

    // Legacy fallback for old cached templates.
    const addForm = document.getElementById('addForm');
    if (!addForm) return false;
    addForm.style.display = 'block';
    addForm.scrollIntoView({behavior: 'smooth', block: 'start'});
    return false;
}

// Make add-payment opening work even when inline handlers are unavailable or stale.
document.addEventListener('DOMContentLoaded', () => {
    const addTarget = document.getElementById('addPaymentModal') || document.getElementById('addForm');
    if (!addTarget) return;

    document.querySelectorAll('button, a').forEach((item) => {
        const text = (item.textContent || '').trim();
        const inline = item.getAttribute('onclick') || '';
        if (text.includes('Добавить платеж') || inline.includes('addForm') || inline.includes('openAddPaymentModal')) {
            item.addEventListener('click', (event) => {
                event.preventDefault();
                showAddPaymentForm();
            });
        }
    });
});

// Clarify orphan receipt cleanup: normal payment deletion already removes attached receipts.
document.addEventListener('DOMContentLoaded', () => {
    const cleanupForm = document.querySelector('form[action="/payments/cleanup-receipts"]');
    if (!cleanupForm) return;

    cleanupForm.onsubmit = () => confirm(
        'Проверить uploads и удалить только файлы чеков, которые уже не привязаны ни к одному платежу? ' +
        'При обычном удалении платежа его чек удаляется сразу.'
    );

    const button = cleanupForm.querySelector('button[type="submit"]');
    if (button) {
        button.textContent = '🧹 Проверить сиротские чеки';
        button.title = 'Обычное удаление платежа сразу удаляет его чек. Эта кнопка нужна только для оставшихся непривязанных файлов.';
    }
});

// Theme toggle
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme') || 'dark';
    const next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    // Also save to backend
    fetch('/settings/theme', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.cookie.match(/_csrf=([^;]+)/)?.[1] || ''
        },
        body: JSON.stringify({theme: next})
    });
}

// Keep localStorage consistent with the theme applied by the page.
(function() {
    const applied = document.documentElement.getAttribute('data-theme');
    if (applied) {
        localStorage.setItem('theme', applied);
    }
})();
