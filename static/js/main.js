/* ===================================================================
   PinPoint — Client-side logic
   =================================================================== */

const PinPoint = (() => {

    const isAuthed = () => window.__AUTH__ === true;

    // ---- Helpers ----

    let _bookmarkSet = new Set();
    let _bookmarksLoaded = false;

    async function loadBookmarkSet() {
        if (!isAuthed()) { _bookmarkSet = new Set(); _bookmarksLoaded = true; return; }
        try {
            const resp = await fetch('/api/bookmarks');
            if (resp.ok) {
                const ids = await resp.json();
                _bookmarkSet = new Set(ids);
            }
        } catch { /* ignore */ }
        _bookmarksLoaded = true;
    }

    function isBookmarked(id) {
        return _bookmarkSet.has(id);
    }

    function starsHTML(rating) {
        const full = Math.round(rating);
        let html = '<span class="stars">';
        for (let i = 1; i <= 5; i++) {
            html += i <= full ? '\u2605' : '\u2606';
        }
        html += '</span>';
        return html;
    }

    function showToast(message, type) {
        type = type || 'info';
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3200);
    }

    function formatDate(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    // ---- Business Card Renderer ----

    function renderBusinessCard(biz) {
        const bookmarked = isBookmarked(biz.id);
        return `
            <div class="business-card" onclick="PinPoint.goToBusiness(${biz.id}, event)">
                <img class="card-image" src="${biz.image_url}" alt="${biz.name}" loading="lazy"
                     onerror="this.style.background='linear-gradient(135deg,#EEF2FF,#F5F3FF)';this.style.height='200px';this.alt='Image unavailable';">
                <div class="card-body">
                    <span class="category-badge ${biz.category}">${biz.category}</span>
                    <div class="card-top">
                        <h3>${biz.name}</h3>
                        <button class="card-bookmark ${bookmarked ? 'bookmarked' : ''}"
                                onclick="event.stopPropagation(); PinPoint.toggleBookmark(${biz.id})"
                                aria-label="Bookmark">
                            ${bookmarked ? '\u2665' : '\u2661'}
                        </button>
                    </div>
                    <p class="card-desc">${biz.description}</p>
                    <div class="card-footer">
                        <div class="card-rating">
                            ${starsHTML(biz.avg_rating)}
                            <span class="rating-text">${biz.avg_rating} (${biz.review_count})</span>
                        </div>
                        <span class="card-address">${biz.address}</span>
                    </div>
                </div>
            </div>
        `;
    }

    // ---- Explore Page ----

    let currentCategory = 'all';
    let currentSort = 'newest';

    async function loadBusinesses() {
        const grid = document.getElementById('business-grid');
        const loader = document.getElementById('grid-loader');
        if (loader) loader.style.display = 'block';

        if (!_bookmarksLoaded) await loadBookmarkSet();

        const params = new URLSearchParams();
        if (currentCategory && currentCategory !== 'all') params.set('category', currentCategory);
        params.set('sort', currentSort);

        try {
            const resp = await fetch('/api/businesses?' + params.toString());
            const data = await resp.json();

            if (data.length === 0) {
                grid.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128269;</div><h2>No businesses found</h2><p>Try a different category or check back later.</p></div>';
                return;
            }
            grid.innerHTML = data.map(renderBusinessCard).join('');
        } catch {
            grid.innerHTML = '<div class="empty-state"><h2>Something went wrong</h2><p>Please refresh the page.</p></div>';
        }
    }

    function initExplorePage() {
        loadBusinesses();

        document.getElementById('category-filters').addEventListener('click', (e) => {
            const btn = e.target.closest('.pill');
            if (!btn) return;
            document.querySelectorAll('#category-filters .pill').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            currentCategory = btn.dataset.category;
            loadBusinesses();
        });

        document.getElementById('sort-select').addEventListener('change', (e) => {
            currentSort = e.target.value;
            loadBusinesses();
        });
    }

    // ---- Business Detail Page ----

    async function initBusinessPage() {
        const page = document.getElementById('detail-page');
        const bizId = parseInt(page.dataset.id);

        if (!_bookmarksLoaded) await loadBookmarkSet();

        try {
            const [bizResp, reviewsResp] = await Promise.all([
                fetch('/api/businesses/' + bizId),
                fetch('/api/businesses/' + bizId + '/reviews'),
            ]);
            const biz = await bizResp.json();
            const reviews = await reviewsResp.json();

            document.getElementById('detail-loader').style.display = 'none';
            document.getElementById('detail-header').style.display = 'flex';
            document.getElementById('reviews-section').style.display = 'block';

            document.getElementById('detail-img').src = biz.image_url;
            document.getElementById('detail-img').alt = biz.name;
            document.getElementById('detail-name').textContent = biz.name;
            document.getElementById('detail-category').textContent = biz.category;
            document.getElementById('detail-category').className = 'category-badge ' + biz.category;
            document.getElementById('detail-rating').innerHTML =
                starsHTML(biz.avg_rating) +
                ' <span class="rating-text">' + biz.avg_rating + ' (' + biz.review_count + ' reviews)</span>';
            document.getElementById('detail-desc').textContent = biz.description;
            document.getElementById('detail-address').textContent = '\uD83D\uDCCD ' + biz.address;
            document.getElementById('detail-phone').textContent = '\uD83D\uDCDE ' + biz.phone;

            updateBookmarkButton(bizId);
            renderReviews(reviews);
            initStarSelector();
        } catch {
            document.getElementById('detail-loader').textContent = 'Failed to load business details.';
        }
    }

    function updateBookmarkButton(bizId) {
        const btn = document.getElementById('detail-bookmark');
        const heart = document.getElementById('detail-heart');
        if (!btn) return;
        const marked = isBookmarked(bizId);
        btn.classList.toggle('bookmarked', marked);
        heart.innerHTML = marked ? '\u2665' : '\u2661';
    }

    function renderReviews(reviews) {
        const list = document.getElementById('reviews-list');
        if (reviews.length === 0) {
            list.innerHTML = '<p style="color:var(--gray-400);text-align:center;padding:24px;">No reviews yet. Be the first to review!</p>';
            return;
        }
        list.innerHTML = reviews.map(r => `
            <div class="review-card">
                <div class="review-top">
                    <span class="review-author">${r.reviewer_name}</span>
                    <span class="review-date">${formatDate(r.created_at)}</span>
                </div>
                <div class="review-stars">${starsHTML(r.rating)}</div>
                <p class="review-comment">${r.comment || ''}</p>
            </div>
        `).join('');
    }

    function initStarSelector() {
        const selector = document.getElementById('star-selector');
        const hidden = document.getElementById('rating-value');
        if (!selector) return;

        selector.addEventListener('click', (e) => {
            const star = e.target.closest('.star-btn');
            if (!star) return;
            const val = parseInt(star.dataset.value);
            hidden.value = val;
            selector.querySelectorAll('.star-btn').forEach((s, i) => {
                s.classList.toggle('active', i < val);
            });
        });

        selector.addEventListener('mouseover', (e) => {
            const star = e.target.closest('.star-btn');
            if (!star) return;
            const val = parseInt(star.dataset.value);
            selector.querySelectorAll('.star-btn').forEach((s, i) => {
                s.classList.toggle('active', i < val);
            });
        });

        selector.addEventListener('mouseleave', () => {
            const current = parseInt(hidden.value) || 0;
            selector.querySelectorAll('.star-btn').forEach((s, i) => {
                s.classList.toggle('active', i < current);
            });
        });
    }

    async function submitReview(e) {
        e.preventDefault();
        const form = document.getElementById('review-form');
        const btn = document.getElementById('submit-review-btn');
        const bizId = parseInt(document.getElementById('detail-page').dataset.id);

        const rating = parseInt(document.getElementById('rating-value').value);
        const comment = document.getElementById('review-comment').value.trim();
        const captchaAnswer = document.getElementById('captcha-answer').value.trim();

        if (!rating || rating < 1) { showToast('Please select a star rating.', 'error'); return false; }
        if (!captchaAnswer) { showToast('Please answer the verification question.', 'error'); return false; }

        btn.disabled = true;
        btn.textContent = 'Submitting...';

        try {
            const resp = await fetch('/api/reviews', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    business_id: bizId,
                    rating: rating,
                    comment: comment,
                    captcha_answer: captchaAnswer,
                }),
            });
            const data = await resp.json();

            if (!resp.ok) {
                if (data.login_required) {
                    window.location.href = '/login?next=/business/' + bizId;
                    return false;
                }
                showToast(data.error || 'Something went wrong.', 'error');
                if (data.new_captcha) {
                    document.getElementById('captcha-question').textContent = data.new_captcha;
                }
                document.getElementById('captcha-answer').value = '';
                btn.disabled = false;
                btn.textContent = 'Submit Review';
                return false;
            }

            showToast('Review submitted! Thank you.', 'success');
            if (data.new_captcha) {
                document.getElementById('captcha-question').textContent = data.new_captcha;
            }

            form.reset();
            document.getElementById('rating-value').value = '0';
            document.querySelectorAll('#star-selector .star-btn').forEach(s => s.classList.remove('active'));

            const reviewsResp = await fetch('/api/businesses/' + bizId + '/reviews');
            const reviews = await reviewsResp.json();
            renderReviews(reviews);

            const bizResp = await fetch('/api/businesses/' + bizId);
            const biz = await bizResp.json();
            document.getElementById('detail-rating').innerHTML =
                starsHTML(biz.avg_rating) +
                ' <span class="rating-text">' + biz.avg_rating + ' (' + biz.review_count + ' reviews)</span>';
        } catch {
            showToast('Network error. Please try again.', 'error');
        }

        btn.disabled = false;
        btn.textContent = 'Submit Review';
        return false;
    }

    // ---- Bookmarks (server-side) ----

    async function toggleBookmark(id) {
        if (!isAuthed()) {
            showToast('Log in to save businesses.', 'info');
            window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
            return;
        }

        const wasBookmarked = _bookmarkSet.has(id);

        try {
            if (wasBookmarked) {
                await fetch('/api/bookmarks/' + id, { method: 'DELETE' });
                _bookmarkSet.delete(id);
                showToast('Removed from saved.', 'info');
            } else {
                await fetch('/api/bookmarks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ business_id: id }),
                });
                _bookmarkSet.add(id);
                showToast('Saved to favorites!', 'success');
            }
        } catch {
            showToast('Could not update bookmark.', 'error');
            return;
        }

        // Update all card bookmark buttons on the page
        document.querySelectorAll('.card-bookmark').forEach(btn => {
            const onclickAttr = btn.getAttribute('onclick') || '';
            const match = onclickAttr.match(/toggleBookmark\((\d+)\)/);
            if (match && parseInt(match[1]) === id) {
                const marked = _bookmarkSet.has(id);
                btn.classList.toggle('bookmarked', marked);
                btn.innerHTML = marked ? '\u2665' : '\u2661';
            }
        });

        updateBookmarkButton(id);
    }

    async function initBookmarksPage() {
        const grid = document.getElementById('business-grid');
        const loader = document.getElementById('grid-loader');
        const empty = document.getElementById('empty-state');

        if (!_bookmarksLoaded) await loadBookmarkSet();
        const bmIds = Array.from(_bookmarkSet);

        if (bmIds.length === 0) {
            if (loader) loader.style.display = 'none';
            grid.style.display = 'none';
            empty.style.display = 'block';
            return;
        }

        try {
            const resp = await fetch('/api/businesses?ids=' + bmIds.join(','));
            const data = await resp.json();

            if (data.length === 0) {
                if (loader) loader.style.display = 'none';
                grid.style.display = 'none';
                empty.style.display = 'block';
                return;
            }

            grid.innerHTML = data.map(renderBusinessCard).join('');
        } catch {
            grid.innerHTML = '<div class="empty-state"><h2>Something went wrong</h2></div>';
        }
    }

    // ---- Deals Page ----

    async function loadDeals(activeOnly) {
        const grid = document.getElementById('deals-grid');
        const empty = document.getElementById('deals-empty');
        const loader = document.getElementById('deals-loader');

        if (loader) { loader.style.display = 'block'; grid.innerHTML = ''; grid.appendChild(loader); }
        if (empty) empty.style.display = 'none';

        const btnActive = document.getElementById('btn-active-deals');
        const btnAll = document.getElementById('btn-all-deals');
        if (btnActive && btnAll) {
            btnActive.classList.toggle('active', activeOnly);
            btnAll.classList.toggle('active', !activeOnly);
        }

        const url = activeOnly ? '/api/deals?active=true' : '/api/deals';
        try {
            const resp = await fetch(url);
            const deals = await resp.json();

            if (deals.length === 0) {
                grid.innerHTML = '';
                if (empty) empty.style.display = 'block';
                return;
            }

            const today = new Date().toISOString().slice(0, 10);
            grid.innerHTML = deals.map(d => {
                const isExpired = d.expiry_date < today;
                return `
                    <div class="deal-card ${isExpired ? 'expired' : ''}">
                        <div class="deal-badge">${d.discount_text}</div>
                        <div class="deal-body">
                            <a href="/business/${d.business_id}" class="deal-business">${d.business_name}</a>
                            <h3>${d.title}</h3>
                            <p class="deal-desc">${d.description}</p>
                            <div class="deal-footer">
                                <div class="coupon-code">
                                    <code>${d.coupon_code}</code>
                                    <button class="btn-copy" onclick="PinPoint.copyCoupon('${d.coupon_code}')">Copy</button>
                                </div>
                                <span class="deal-expiry ${isExpired ? 'expired-text' : ''}">
                                    ${isExpired ? 'Expired' : 'Expires ' + formatDate(d.expiry_date)}
                                </span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch {
            grid.innerHTML = '<div class="empty-state"><h2>Failed to load deals</h2></div>';
        }
    }

    function initDealsPage() {
        loadDeals(true);
    }

    function copyCoupon(code) {
        navigator.clipboard.writeText(code).then(
            () => showToast('Coupon code copied!', 'success'),
            () => showToast('Could not copy. Code: ' + code, 'info')
        );
    }

    // ---- Auth ----

    async function handleLogin(e) {
        e.preventDefault();
        const btn = document.getElementById('login-btn');
        const errEl = document.getElementById('login-error');
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        errEl.style.display = 'none';
        btn.disabled = true;
        btn.textContent = 'Logging in...';

        try {
            const resp = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await resp.json();

            if (!resp.ok) {
                errEl.textContent = data.error;
                errEl.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Log In';
                return false;
            }

            const params = new URLSearchParams(window.location.search);
            window.location.href = params.get('next') || '/';
        } catch {
            errEl.textContent = 'Network error. Please try again.';
            errEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Log In';
        }
        return false;
    }

    async function handleSignup(e) {
        e.preventDefault();
        const btn = document.getElementById('signup-btn');
        const errEl = document.getElementById('signup-error');
        const display_name = document.getElementById('signup-display-name').value.trim();
        const username = document.getElementById('signup-username').value.trim();
        const password = document.getElementById('signup-password').value;

        errEl.style.display = 'none';
        btn.disabled = true;
        btn.textContent = 'Creating account...';

        try {
            const resp = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name, username, password }),
            });
            const data = await resp.json();

            if (!resp.ok) {
                errEl.textContent = data.error;
                errEl.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Create Account';
                return false;
            }

            window.location.href = '/';
        } catch {
            errEl.textContent = 'Network error. Please try again.';
            errEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Create Account';
        }
        return false;
    }

    function demoLogin() {
        document.getElementById('login-username').value = 'demo';
        document.getElementById('login-password').value = 'demo123';
        document.getElementById('login-form').dispatchEvent(new Event('submit', { cancelable: true }));
    }

    async function logout() {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
        } catch { /* ignore */ }
        window.location.href = '/';
    }

    // ---- User menu toggle ----

    document.addEventListener('DOMContentLoaded', () => {
        const menuBtn = document.getElementById('user-menu-btn');
        const dropdown = document.getElementById('user-dropdown');
        if (menuBtn && dropdown) {
            menuBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.toggle('open');
            });
            document.addEventListener('click', () => dropdown.classList.remove('open'));
        }
    });

    // ---- Navigation ----

    function goToBusiness(id, event) {
        if (event && (event.target.closest('.card-bookmark') || event.target.closest('button'))) return;
        window.location.href = '/business/' + id;
    }

    // ---- Public API ----
    return {
        initExplorePage,
        initBusinessPage,
        initBookmarksPage,
        initDealsPage,
        toggleBookmark,
        submitReview,
        loadDeals,
        copyCoupon,
        goToBusiness,
        handleLogin,
        handleSignup,
        demoLogin,
        logout,
    };

})();
