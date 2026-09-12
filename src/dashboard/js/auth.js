/**
 * Authentication module for Dashboard
 */

class AuthManager {
    constructor() {
        this.token = sessionStorage.getItem('auth_token');
        this.agentId = sessionStorage.getItem('agent_id');
        this.expiresAt = sessionStorage.getItem('expires_at');
    }

    isAuthenticated() {
        if (!this.token || !this.expiresAt) return false;
        
        // Check if expired
        const expires = new Date(this.expiresAt);
        if (new Date() >= expires) {
            this.clearSession();
            return false;
        }
        return true;
    }

    getAuthHeader() {
        return this.token ? { 'Authorization': `Bearer ${this.token}` } : {};
    }

    async login(commanderId, passphrase) {
        try {
            const apiBase = (typeof API_BASE !== 'undefined') ? API_BASE : 'http://localhost:8000/api/v1';
            const response = await fetch(`${apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    commander_id: commanderId,
                    passphrase: passphrase
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Login failed');
            }

            const data = await response.json();
            this.setSession(data);
            return true;
        } catch (error) {
            console.error('Login error:', error);
            throw error;
        }
    }

    setSession(data) {
        this.token = data.token;
        this.agentId = data.agent_id;
        this.expiresAt = data.expires_at;
        
        sessionStorage.setItem('auth_token', this.token);
        sessionStorage.setItem('agent_id', this.agentId);
        sessionStorage.setItem('expires_at', this.expiresAt);
        
        // Trigger event
        window.dispatchEvent(new CustomEvent('auth-changed', { detail: { authenticated: true } }));
    }

    clearSession() {
        this.token = null;
        this.agentId = null;
        this.expiresAt = null;
        
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('agent_id');
        sessionStorage.removeItem('expires_at');
        
        // Trigger event
        window.dispatchEvent(new CustomEvent('auth-changed', { detail: { authenticated: false } }));
        
        this.showLoginPrompt();
    }

    showLoginPrompt() {
        const modal = document.getElementById('login-modal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }
    
    hideLoginPrompt() {
        const modal = document.getElementById('login-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }
}

// Global instance
window.authManager = new AuthManager();

// Setup DOM event listeners when loaded
document.addEventListener('DOMContentLoaded', () => {
    // If not authenticated, show login prompt immediately
    if (!window.authManager.isAuthenticated()) {
        window.authManager.showLoginPrompt();
    }
    
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const commanderId = document.getElementById('login-commander-id').value;
            const passphrase = document.getElementById('login-passphrase').value;
            const errorEl = document.getElementById('login-error');
            
            try {
                errorEl.textContent = '';
                errorEl.classList.add('hidden');
                
                await window.authManager.login(commanderId, passphrase);
                window.authManager.hideLoginPrompt();
            } catch (err) {
                errorEl.textContent = err.message || 'Authentication failed';
                errorEl.classList.remove('hidden');
            }
        });
    }
});
