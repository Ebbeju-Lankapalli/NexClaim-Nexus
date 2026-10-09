/**
 * NexClaim Multi-Language i18n Engine
 * Lightweight, Vanilla JS Translation Module
 */

window.I18N = (function() {
    let currentLang = localStorage.getItem('nexclaim_lang') || 'en';
    let dictionary = {};

    const loadDictionary = async (lang) => {
        try {
            const res = await fetch(`/static/i18n/${lang}.json`);
            if (!res.ok) throw new Error('Dictionary not found');
            dictionary = await res.json();
            return true;
        } catch (err) {
            console.error(`Failed to load dictionary for ${lang}:`, err);
            return false;
        }
    };

    const updateDOM = () => {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const targetAttr = el.getAttribute('data-i18n-target'); // e.g. 'placeholder'
            
            const translated = t(key);
            if (!translated) return;

            if (targetAttr) {
                el.setAttribute(targetAttr, translated);
            } else if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button')) {
                el.value = translated;
            } else {
                el.innerHTML = translated;
            }
        });
    };

    const t = (key, fallback = '') => {
        return dictionary[key] || fallback || key;
    };

    const setLanguage = async (lang) => {
        if (!['en', 'hi', 'te'].includes(lang)) return;
        
        currentLang = lang;
        localStorage.setItem('nexclaim_lang', lang);
        
        // Update language switcher UI elements if any
        document.querySelectorAll('.lang-switcher-select').forEach(sel => {
            if(sel.value !== lang) sel.value = lang;
        });
        
        const currentLangBtn = document.getElementById('currentLangBtn');
        if (currentLangBtn) {
            if (lang === 'hi') currentLangBtn.innerHTML = '🇮🇳 HI ▼';
            else if (lang === 'te') currentLangBtn.innerHTML = '🇮🇳 TE ▼';
            else currentLangBtn.innerHTML = '🇬🇧 EN ▼';
        }
        
        await loadDictionary(lang);
        updateDOM();
        
        // Dispatch event for dynamic UI components (like Policyholder dashboard)
        window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));
    };

    // Theme Management
    const toggleTheme = () => {
        const isDark = document.body.classList.toggle('dark-mode');
        localStorage.setItem('nexclaim_theme', isDark ? 'dark' : 'light');
        document.querySelectorAll('.theme-btn').forEach(b => {
            b.innerHTML = isDark ? '☀️' : '🌙';
        });
    };

    const setupTheme = () => {
        let theme = localStorage.getItem('nexclaim_theme') || 'light';
        if (theme === 'dark') document.body.classList.add('dark-mode');
        else document.body.classList.remove('dark-mode');
        
        // Ensure buttons have the right initial state
        document.querySelectorAll('.theme-btn').forEach(b => {
            b.innerHTML = theme === 'dark' ? '☀️' : '🌙';
        });
    };

    // Initialization
    const init = async () => {
        await loadDictionary(currentLang);
        
        // Expose to window immediately so inline scripts can use it
        window.t = t;
        window.toggleTheme = toggleTheme;
        
        // Initial DOM update when DOM is fully loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                updateDOM();
                setupTheme();
            });
        } else {
            updateDOM();
            setupTheme();
        }
    };

    init();

    return {
        getLang: () => currentLang,
        setLanguage,
        t,
        updateDOM
    };
})();

// Global alias for quick translations in JS
window.t = window.I18N.t;
