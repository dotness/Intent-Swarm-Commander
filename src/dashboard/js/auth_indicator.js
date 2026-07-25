/* Auth indicator component */

/**
 * Update the UI authentication indicator based on token presence.
 * In MVP, we mock this by checking localStorage.
 */
function updateAuthIndicator() {
    const indicator = document.getElementById('auth-indicator');
    if (!indicator) return;

    // MVP mock: just assume we have a commander token
    // In full implementation, this checks the actual JIT/OAuth token
    const isAuthenticated = true; 
    const commanderId = "commander-default";

    if (isAuthenticated) {
        indicator.innerHTML = `
            <span class="auth-badge auth-badge--authenticated">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                </svg>
                Auth: ${commanderId}
            </span>
        `;
    } else {
        indicator.innerHTML = `
            <span class="auth-badge auth-badge--unauthenticated">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
                Not Authenticated
            </span>
        `;
    }
}

window.AuthIndicator = {
    update: updateAuthIndicator
};
