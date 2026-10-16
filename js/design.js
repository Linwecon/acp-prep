/* Shared visual elements, local SVG icons and reading preferences. */
(function (ACP) {
    const paths = {
        book: '<path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z"/><path d="M12 6v14"/>',
        grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
        target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
        exam: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10h6M9 14h6M9 18h3"/>',
        code: '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16"/>',
        arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
        star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/>',
        review: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',
        check: '<path d="m5 12 4 4L19 6"/>',
        info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
        sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
        settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
        trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
        menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
        search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
        lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
        eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
        'eye-off': '<path d="m3 3 18 18M9 5.5a11 11 0 0 1 3-.5c7 0 10 7 10 7a16 16 0 0 1-3 4M6 6c-3 2-4 6-4 6s3 7 10 7a12 12 0 0 0 5-1M10 10a3 3 0 0 0 4 4"/>',
        chat: '<path d="M21 11a8 8 0 0 1-8 8H6l-4 3V11a9 9 0 0 1 19 0Z"/><path d="M7 10h10M7 14h6"/>',
        close: '<path d="m6 6 12 12M6 18 18 6"/>',
        shuffle: '<path d="M3 6h3c4 0 8 12 12 12h3m-4-4 4 4-4 4M3 18h3c1 0 3-2 4-4m4-4c1-2 3-4 4-4h3m-4-4 4 4-4 4"/>',
        layers: '<path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>'
    };
    ACP.icon = name => '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || paths.book) + '</svg>';
    ACP.decorateIcons = function (root = document) {
        root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = ACP.icon(el.dataset.icon); });
    };
    ACP.readingSize = 16;
    ACP.adjustReadingSize = function (step) {
        ACP.readingSize = Math.max(14, Math.min(20, ACP.readingSize + step));
        document.documentElement.style.setProperty('--reading-size', ACP.readingSize + 'px');
        document.querySelectorAll('[data-reading-size]').forEach(el => { el.textContent = ACP.readingSize; });
        try { localStorage.setItem('acp_reading_size', ACP.readingSize); } catch (e) {}
    };
    ACP.readingControls = () => `<div class="reading-controls" role="group" aria-label="正文字号"><button onclick="ACP.adjustReadingSize(-1)" aria-label="缩小正文字号">A−</button><span data-reading-size aria-live="polite">${ACP.readingSize}</span><button onclick="ACP.adjustReadingSize(1)" aria-label="放大正文字号">A+</button></div>`;
    ACP.initDesign = function () {
        try { ACP.readingSize = Number(localStorage.getItem('acp_reading_size')) || 16; } catch (e) {}
        ACP.adjustReadingSize(0);
        ACP.decorateIcons();
        // Dialogs share keyboard behavior with the visual treatment.
        const dialogs = [...document.querySelectorAll('.modal[aria-modal="true"]')];
        let active = null, previousFocus = null;
        const refreshDialog = () => {
            const next = dialogs.find(el => el.classList.contains('show')) || null;
            if (next === active) return;
            if (next) {
                if (!active) previousFocus = document.activeElement;
                active = next;
                setTimeout(() => {
                    if (active !== next) return;
                    const target = [...next.querySelectorAll('input, select, button')].find(el => !el.disabled && el.getClientRects().length);
                    if (target) target.focus({ preventScroll: true });
                }, 0);
            } else {
                active = null;
                if (previousFocus && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
            }
        };
        const observer = new MutationObserver(refreshDialog);
        dialogs.forEach(el => observer.observe(el, { attributes: true, attributeFilter: ['class'] }));
        document.addEventListener('keydown', e => {
            if (e.key !== 'Tab' || !active) return;
            const targets = [...active.querySelectorAll('a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]')].filter(el => el.getClientRects().length);
            if (!targets.length) return;
            const first = targets[0], last = targets[targets.length - 1];
            if (!active.contains(document.activeElement) || (!e.shiftKey && document.activeElement === last)) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
    };
    ACP.mobilePractice = function () {
        const last = ACP.state.store.last;
        if (last && ACP.ID_MAP[last.id]) ACP.resumeLast();
        else ACP.openChapter(ACP.CH_IDS[0]);
    };
    ACP.updateMobileNav = function () {
        const view = ACP.state.ui.view;
        const active = view === 'tutorial' ? 'study' : ['chapter', 'wrong', 'fav'].includes(view) ? 'chapter' : view;
        document.querySelectorAll('[data-mobile-nav]').forEach(el => {
            const selected = el.dataset.mobileNav === active;
            el.classList.toggle('active', selected);
            if (selected) el.setAttribute('aria-current', 'page');
            else el.removeAttribute('aria-current');
        });
    };
})(window.ACP);
