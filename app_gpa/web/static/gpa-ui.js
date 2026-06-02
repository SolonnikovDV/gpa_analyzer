(function(global) {
  'use strict';

  var AGENT_SESSION_KEY = 'gpa_agent_session';

  global.GpaWait = {
    _depth: 0,
    _layer: null,

    _ensureLayer: function() {
      if (this._layer) return this._layer;
      var layer = document.getElementById('gpa-wait-layer');
      if (!layer) {
        layer = document.createElement('div');
        layer.id = 'gpa-wait-layer';
        layer.className = 'gpa-wait-layer';
        layer.setAttribute('aria-hidden', 'true');
        layer.innerHTML =
          '<div class="gpa-wait-layer__backdrop"></div>' +
          '<div class="gpa-wait-panel" role="status" aria-live="polite">' +
            '<div class="gpa-wait-panel__orb" aria-hidden="true"></div>' +
            '<div class="gpa-wait-panel__message" data-gpa-wait-message>Ожидание…</div>' +
            '<div class="gpa-wait-panel__sub" data-gpa-wait-sub></div>' +
            '<div class="gpa-wait-panel__trace" data-gpa-wait-trace style="display:none;">' +
              '<div class="gpa-wait-panel__trace-title">Ход дебатов ролей</div>' +
              '<div class="gpa-wait-panel__trace-body" data-gpa-wait-trace-body></div>' +
              '<div class="gpa-wait-panel__trace-consensus" data-gpa-wait-consensus style="display:none;"></div>' +
            '</div>' +
          '</div>';
        document.body.appendChild(layer);
      }
      this._layer = layer;
      return layer;
    },

    show: function(opts) {
      opts = opts || {};
      var layer = this._ensureLayer();
      this._depth += 1;
      layer.classList.add('is-visible');
      layer.setAttribute('aria-hidden', 'false');
      layer.dataset.mode = opts.mode || 'default';
      this.setStatus(opts.message || 'Ожидание…', opts.subtitle || '');
      this.setTranscript([], '');
      if (opts.anchor) this.anchor(opts.anchor, opts.message, opts.subtitle);
    },

    hide: function() {
      this._depth = Math.max(0, this._depth - 1);
      if (this._depth > 0) return;
      var layer = this._ensureLayer();
      layer.classList.remove('is-visible');
      layer.setAttribute('aria-hidden', 'true');
      this.setTranscript([], '');
      this.unanchor();
    },

    setStatus: function(message, subtitle) {
      var layer = this._ensureLayer();
      var msg = layer.querySelector('[data-gpa-wait-message]');
      var sub = layer.querySelector('[data-gpa-wait-sub]');
      if (msg && message != null) msg.textContent = String(message);
      if (sub && subtitle != null) sub.textContent = String(subtitle);
    },

    anchor: function(el, message, subtitle) {
      if (!el) return;
      el.classList.add('gpa-wait-anchor');
      if (message) el.setAttribute('data-gpa-wait-label', message);
      if (subtitle) el.setAttribute('data-gpa-wait-sub', subtitle);
    },

    unanchor: function() {
      document.querySelectorAll('.gpa-wait-anchor').forEach(function(node) {
        node.classList.remove('gpa-wait-anchor');
        node.removeAttribute('data-gpa-wait-label');
        node.removeAttribute('data-gpa-wait-sub');
      });
    },

    setTranscript: function(trace, consensus) {
      var layer = this._ensureLayer();
      var wrap = layer.querySelector('[data-gpa-wait-trace]');
      var body = layer.querySelector('[data-gpa-wait-trace-body]');
      var cons = layer.querySelector('[data-gpa-wait-consensus]');
      var rows = Array.isArray(trace) ? trace : [];
      if (!wrap || !body || !cons) return;
      if (!rows.length && !(consensus || '').trim()) {
        wrap.style.display = 'none';
        body.innerHTML = '';
        cons.style.display = 'none';
        cons.textContent = '';
        return;
      }
      wrap.style.display = 'block';
      body.innerHTML = rows.map(function(r) {
        var round = r && r.round != null ? String(r.round) : '–';
        var mode = r && r.mode ? String(r.mode) : 'step';
        var role = r && r.role_focus ? String(r.role_focus) : 'team';
        var text = r && r.text ? String(r.text) : '';
        var textSafe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        if (textSafe.length > 420) textSafe = textSafe.slice(0, 420) + '...';
        return '<div class="gpa-wait-panel__trace-row"><b>#' + round + ' · ' + mode + ' · ' + role + '</b><br><span>' + textSafe + '</span></div>';
      }).join('');
      var cc = (consensus || '').trim();
      if (cc) {
        cons.style.display = 'block';
        cons.textContent = 'CONSENSUS: ' + cc;
      } else {
        cons.style.display = 'none';
        cons.textContent = '';
      }
    }
  };

  global.GpaAgentSession = {
    key: AGENT_SESSION_KEY,

    read: function() {
      try {
        var raw = sessionStorage.getItem(AGENT_SESSION_KEY);
        return raw ? JSON.parse(raw) : null;
      } catch (e) {
        return null;
      }
    },

    save: function(payload) {
      try {
        var prev = this.read() || {};
        sessionStorage.setItem(AGENT_SESSION_KEY, JSON.stringify(Object.assign({}, prev, payload || {})));
      } catch (e) {}
    },

    clear: function() {
      try {
        sessionStorage.removeItem(AGENT_SESSION_KEY);
        sessionStorage.removeItem('gpa_agent_last_profile_name');
        sessionStorage.removeItem('gpa_agent_chat_model');
        sessionStorage.removeItem('gpa_agent_embedding_model');
        sessionStorage.removeItem('gpa_agent_provider');
      } catch (e) {}
    },

    migrateFromLocalStorage: function() {
      try {
        if (sessionStorage.getItem(AGENT_SESSION_KEY)) return;
        var profile = (localStorage.getItem('gpa_agent_last_profile_name') || '').trim();
        var chat = (localStorage.getItem('gpa_agent_chat_model') || '').trim();
        var emb = (localStorage.getItem('gpa_agent_embedding_model') || '').trim();
        if (!profile && !chat && !emb) return;
        this.save({
          profileName: profile || '',
          chatModel: chat || '',
          embModel: emb || '',
          authenticated: false
        });
        if (profile) sessionStorage.setItem('gpa_agent_last_profile_name', profile);
        if (chat) sessionStorage.setItem('gpa_agent_chat_model', chat);
        if (emb) sessionStorage.setItem('gpa_agent_embedding_model', emb);
      } catch (e) {}
    },

    getProfileName: function() {
      try {
        return (sessionStorage.getItem('gpa_agent_last_profile_name') || '').trim();
      } catch (e) {
        return '';
      }
    },

    setProfileName: function(name) {
      try {
        if (name) sessionStorage.setItem('gpa_agent_last_profile_name', name.trim());
      } catch (e) {}
      this.save({ profileName: (name || '').trim() });
    }
  };

  global.GpaLog = {
    bindCounter: function(logEl, countEl) {
      if (!logEl || !countEl) return;
      var update = function() {
        var n = logEl.querySelectorAll('.log-entry').length;
        countEl.textContent = n + ' ' + (n === 1 ? 'строка' : (n >= 2 && n <= 4 ? 'строки' : 'строк'));
      };
      update();
      var obs = new MutationObserver(update);
      obs.observe(logEl, { childList: true });
    }
  };

  /** Остановка EventSource и poll-интервалов (bfcache / back navigation). */
  global.GpaJobPage = {
    _es: null,
    _intervals: [],

    trackInterval: function(id) {
      if (id != null) this._intervals.push(id);
      return id;
    },

    bindEventSource: function(url, onMessage, onError) {
      this.closeEventSource();
      var es = new EventSource(url);
      this._es = es;
      es.onmessage = onMessage;
      es.onerror = onError || function() {
        try { es.close(); } catch (e) {}
      };
      return es;
    },

    closeEventSource: function() {
      if (this._es) {
        try { this._es.close(); } catch (e) {}
        this._es = null;
      }
    },

    stopAll: function() {
      this.closeEventSource();
      this._intervals.forEach(function(id) { clearInterval(id); });
      this._intervals = [];
    }
  };

  window.addEventListener('pagehide', function() {
    global.GpaJobPage.stopAll();
  });

  /** Плашка токенов: GigaChat (токены) и DeepSeek (USD balance). */
  global.GpaTokenStrip = {
    apply: function(data, opts) {
      opts = opts || {};
      var provider = String(opts.provider || data.provider || 'gigachat').toLowerCase();
      var block = (data.by_provider && data.by_provider[provider]) ? data.by_provider[provider] : data;
      var u = block.used || data.used || {};
      var last = block.last_request || data.last_request || null;
      var isDs = provider === 'deepseek';

      var elProv = document.getElementById('token-provider-label');
      if (elProv) elProv.textContent = isDs ? 'DeepSeek' : 'GigaChat';

      var elTotal = document.getElementById('token-used');
      var elPrompt = document.getElementById('token-prompt');
      var elComp = document.getElementById('token-completion');
      var elSess = document.getElementById('token-sessions');
      var elAv = document.getElementById('token-available');
      var elPrec = document.getElementById('token-precached');
      var elLastP = document.getElementById('token-last-prompt');
      var elLastC = document.getElementById('token-last-completion');
      var elLastWrap = document.getElementById('token-last-wrap');
      var elPrecWrap = document.getElementById('token-precached-wrap');
      var el429Wrap = document.getElementById('token-429-wrap');

      if (elTotal) elTotal.textContent = (u.total_tokens || 0).toLocaleString();
      if (elPrompt) elPrompt.textContent = (u.prompt_tokens || 0).toLocaleString();
      if (elComp) elComp.textContent = (u.completion_tokens || 0).toLocaleString();
      if (elSess) elSess.textContent = (u.sessions || 0).toLocaleString();

      if (elLastP) elLastP.textContent = last ? (last.prompt_tokens || 0).toLocaleString() : '—';
      if (elLastC) elLastC.textContent = last ? (last.completion_tokens || 0).toLocaleString() : '—';
      if (elLastWrap) elLastWrap.style.display = '';

      if (elPrec) elPrec.textContent = (u.precached_prompt_tokens || 0).toLocaleString();
      if (elPrecWrap) elPrecWrap.style.display = isDs ? 'none' : '';
      if (el429Wrap) el429Wrap.style.display = isDs ? 'none' : '';

      if (elAv) {
        var av = block.available;
        if (isDs) {
          var bal = block.total_balance || data.total_balance || block.available_label;
          var cur = block.currency || data.currency || 'USD';
          if (bal != null && bal !== '') {
            elAv.textContent = (cur === 'USD' ? '$' : '') + bal + (cur !== 'USD' ? ' ' + cur : '');
            elAv.classList.remove('na');
          } else {
            elAv.textContent = '—';
            elAv.classList.add('na');
          }
          var be = block.balance_error || data.balance_error || '';
          if (block.balance_source === 'deepseek_user_balance') {
            elAv.title = 'Баланс DeepSeek (GET /user/balance). granted=' +
              (block.granted_balance || '0') + ', topped_up=' + (block.topped_up_balance || '0');
          } else if (be) {
            elAv.title = be;
          } else {
            elAv.removeAttribute('title');
          }
        } else {
          elAv.textContent = av != null ? av.toLocaleString() : '—';
          elAv.classList.toggle('na', av == null);
          var src = block.balance_source || data.balance_source || '';
          var be2 = block.balance_error || data.balance_error || '';
          if (src === 'freemium_estimate') {
            elAv.title = 'Оценка: лимит GigaChat Lite минус учтённые total_tokens. GET /balance при pay-as-you-go недоступен (403).';
          } else if (src === 'get_balance' && (block.balance_by_model || data.balance_by_model)) {
            var models = block.balance_by_model || data.balance_by_model || [];
            elAv.title = 'Остаток из GET /balance: ' + models.map(function(x) {
              return (x.model || '?') + '=' + (x.tokens != null ? x.tokens : '—');
            }).join(', ');
          } else if (be2) {
            elAv.title = be2;
          } else {
            elAv.removeAttribute('title');
          }
        }
      }

      var el429 = document.getElementById('token-rate-limit');
      if (el429 && !isDs) {
        var c429 = 0;
        try { c429 = parseInt(sessionStorage.getItem('gpa_rate_limit_429') || '0', 10) || 0; } catch (e) {}
        if (opts.rateLimit429 != null) c429 = opts.rateLimit429;
        el429.textContent = c429.toLocaleString();
        el429.classList.toggle('warn', c429 > 0);
      }

      return { provider: provider, available: isDs ? block.total_balance : block.available };
    }
  };
})(window);
