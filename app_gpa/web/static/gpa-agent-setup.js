(function(global) {
  'use strict';

  /**
   * Server-driven agent setup flow.
   * Единый pipeline: plan from /api/agent/flow/plan → шаги PROFILE / SELECT_SLOTS.
   */
  global.GpaAgentSetup = {
    providers: [],
    llmMode: 'off',
    flowPlan: null,
    _stepIndex: 0,
    _callbacks: {},
    _prevMode: 'off',

    init: function(opts) {
      opts = opts || {};
      this._callbacks = {
        isAgentScenario: opts.isAgentScenario || function() { return false; },
        setProvider: opts.setProvider || function() {},
        syncMultiAgent: opts.syncMultiAgent || function() {},
        openProfileModal: opts.openProfileModal || function() {},
        refreshUi: opts.refreshUi || function() {},
        onModeChange: opts.onModeChange || function() {}
      };
      this._mountEl = document.getElementById('llmProviderSwitch');
      this._sectionEl = document.getElementById('llmProviderSection');
      this._statusEl = document.getElementById('llmProviderStatus');
      this._bindMultiPickModal();
      this._bindProfileWizardHooks();
      return this.loadProviders().then(function() {
        this.restoreFromSession();
        this.renderSwitch();
        this.syncSectionVisibility();
        return this;
      }.bind(this));
    },

    loadProviders: function() {
      var self = this;
      return fetch('/api/agent/providers')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          self.providers = (data && data.providers) || (data && data.data && data.data.providers) || [];
          return self.providers;
        })
        .catch(function() {
          self.providers = [
            { id: 'gigachat', label: 'GigaChat', configured: false }
          ];
          return self.providers;
        });
    },

    restoreFromSession: function() {
      var sess = global.GpaAgentSession && GpaAgentSession.read();
      if (sess && sess.provider) this.llmMode = sess.provider;
      else {
        try {
          var p = sessionStorage.getItem('gpa_agent_provider');
          if (p) this.llmMode = p;
        } catch (e) {}
      }
      this._prevMode = this.llmMode;
    },

    syncSectionVisibility: function() {
      if (!this._sectionEl) return;
      var show = this._callbacks.isAgentScenario();
      this._sectionEl.style.display = show ? '' : 'none';
      if (!show && this.llmMode !== 'off') {
        this.llmMode = 'off';
        this.renderSwitch();
      }
    },

    renderSwitch: function() {
      var el = this._mountEl;
      if (!el) return;
      var self = this;
      el.innerHTML = '';
      this.providers.forEach(function(p) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'llm-provider-switch__btn';
        btn.dataset.llmMode = p.id;
        btn.textContent = p.label || p.id;
        if (self.llmMode === p.id) btn.classList.add('is-active');
        btn.addEventListener('click', function() { self.selectMode(p.id, true); });
        el.appendChild(btn);
      });
      this._updateStatus();
    },

    fetchFlowPlan: function(mode, extra) {
      var qs = new URLSearchParams();
      qs.set('mode', 'single');
      qs.set('stack', (extra && extra.stack) || 'greenplum');
      if (mode !== 'off') qs.set('provider', mode);
      if (extra && extra.selected_provider_ids) qs.set('selected_provider_ids', extra.selected_provider_ids.join(','));
      return fetch('/api/agent/flow/plan?' + qs.toString())
        .then(function(r) { return r.json(); })
        .then(function(data) {
          return (data && data.data) || data;
        });
    },

    selectMode: function(mode, openFlow) {
      if (!this._callbacks.isAgentScenario()) return;
      var next = (mode || 'off').toLowerCase();
      var isKnownProvider = this.providers.some(function(p) { return p.id === next; });
      this._prevMode = this.llmMode;
      this.llmMode = next;
      this.renderSwitch();
      this._callbacks.syncMultiAgent(false);
      if (next !== 'off' && isKnownProvider) {
        this._callbacks.setProvider(next, false);
      }
      this._callbacks.onModeChange(next);
      if (!openFlow) return;
      var self = this;
      if (next !== 'off' && isKnownProvider) {
        this.fetchFlowPlan(next).then(function(plan) {
          self.flowPlan = plan;
          self._stepIndex = 0;
          self._runCurrentStep();
        });
      }
    },

    _runCurrentStep: function() {
      if (!this.flowPlan || !this.flowPlan.steps) return;
      var step = this.flowPlan.steps[this._stepIndex];
      if (!step) return;
      if (step.kind === 'select_slots') {
        this.openMultiAgentPickModal();
        return;
      }
      if (step.kind === 'profile' && step.slot) {
        this._openProfileForSlot(step.slot, this._stepIndex + 1, this._profileStepsTotal());
        return;
      }
    },

    _profileStepsTotal: function() {
      if (!this.flowPlan || !this.flowPlan.steps) return 1;
      return this.flowPlan.steps.filter(function(s) { return s.kind === 'profile'; }).length;
    },

    _openProfileForSlot: function(slot, stepNum, total) {
      var provider = slot.provider_id;
      var titleEl = document.getElementById('agentContextModalLabel');
      var wizardEl = document.getElementById('agentProfileWizardHint');
      if (titleEl) titleEl.textContent = 'Профиль ' + stepNum + ' из ' + total + ': ' + (slot.label || provider);
      if (wizardEl) {
        wizardEl.style.display = 'block';
        wizardEl.textContent = 'Единый флоу · роли: ' + ((slot.governance_roles || []).join(', ') || '—');
      }
      var provSel = document.getElementById('agentProviderSelect');
      if (provSel) {
        provSel.value = provider;
        provSel.disabled = true;
      }
      this._callbacks.setProvider(provider, false);
      this._callbacks.openProfileModal(provider);
      var modalEl = document.getElementById('agentContextModal');
      if (modalEl && typeof bootstrap !== 'undefined') bootstrap.Modal.getOrCreateInstance(modalEl).show();
    },

    openMultiAgentPickModal: function() {
      var self = this;
      this.fetchFlowPlan('multi').then(function(plan) {
        self.flowPlan = plan;
        self._populateMultiPickList(plan);
        var modalEl = document.getElementById('multiAgentPickModal');
        if (modalEl && typeof bootstrap !== 'undefined') bootstrap.Modal.getOrCreateInstance(modalEl).show();
      });
    },

    _populateMultiPickList: function(plan) {
      var list = document.getElementById('multiAgentPickList');
      if (!list) return;
      list.innerHTML = '';
      var slots = (plan && plan.slots) || this.providers.map(function(p) {
        return { provider_id: p.id, label: p.label, default_chat_model: p.default_chat_model };
      });
      var active = this.getMultiActiveProviders();
      slots.forEach(function(slot) {
        var pid = slot.provider_id;
        var row = document.createElement('div');
        row.className = 'multi-agent-pick-row border rounded p-2 mb-2';
        row.innerHTML =
          '<div class="form-check mb-1">' +
            '<input class="form-check-input multi-agent-pick-cb" type="checkbox" id="ma_pick_' + pid + '" data-provider="' + pid + '">' +
            '<label class="form-check-label fw-semibold" for="ma_pick_' + pid + '">' + (slot.label || pid) + '</label>' +
          '</div>' +
          '<label class="form-label small mb-0">Chat-модель</label>' +
          '<select class="form-select form-select-sm multi-agent-pick-model" data-provider="' + pid + '">' +
            '<option value="' + (slot.default_chat_model || '') + '">' + (slot.default_chat_model || '—') + '</option>' +
          '</select>' +
          (slot.governance_roles && slot.governance_roles.length
            ? '<div class="form-text">Роли governance: ' + slot.governance_roles.join(', ') + '</div>'
            : '');
        list.appendChild(row);
        var cb = row.querySelector('.multi-agent-pick-cb');
        if (cb && active.indexOf(pid) >= 0) cb.checked = true;
      });
    },

    _bindMultiPickModal: function() {
      var self = this;
      var btn = document.getElementById('multiAgentPickConfirm');
      var modalEl = document.getElementById('multiAgentPickModal');
      if (!btn || !modalEl) return;
      btn.addEventListener('click', function() {
        var checked = [];
        var models = {};
        document.querySelectorAll('.multi-agent-pick-cb:checked').forEach(function(cb) {
          var pid = cb.getAttribute('data-provider');
          if (!pid) return;
          checked.push(pid);
          var sel = document.querySelector('.multi-agent-pick-model[data-provider="' + pid + '"]');
          if (sel && sel.value) models[pid] = sel.value;
        });
        if (!checked.length) {
          var err = document.getElementById('multiAgentPickError');
          if (err) { err.textContent = 'Выберите хотя бы один LLM.'; err.style.display = 'block'; }
          return;
        }
        var errEl = document.getElementById('multiAgentPickError');
        if (errEl) errEl.style.display = 'none';
        self.saveMultiActiveProviders(checked, models);
        if (checked[0]) self._callbacks.setProvider(checked[0], false);
        bootstrap.Modal.getInstance(modalEl).hide();
        self.fetchFlowPlan('multi', { selected_provider_ids: checked }).then(function(plan) {
          self.flowPlan = plan;
          self._stepIndex = 0;
          for (var i = 0; i < plan.steps.length; i++) {
            if (plan.steps[i].kind === 'profile') {
              self._stepIndex = i;
              break;
            }
          }
          self._runCurrentStep();
        });
      });
    },

    getMultiActiveProviders: function() {
      var sess = global.GpaAgentSession && GpaAgentSession.read();
      if (sess && Array.isArray(sess.multiAgentActiveProviders)) return sess.multiAgentActiveProviders.slice();
      try {
        var raw = sessionStorage.getItem('gpa_multi_agent_providers');
        return raw ? JSON.parse(raw) : [];
      } catch (e) { return []; }
    },

    saveMultiActiveProviders: function(ids, modelsByProvider) {
      try { sessionStorage.setItem('gpa_multi_agent_providers', JSON.stringify(ids || [])); } catch (e) {}
      if (global.GpaAgentSession) {
        GpaAgentSession.save({ multiAgentActiveProviders: ids || [], multiAgentModels: modelsByProvider || {} });
      }
    },

    _bindProfileWizardHooks: function() {
      var self = this;
      var modalEl = document.getElementById('agentContextModal');
      if (!modalEl) return;
      modalEl.addEventListener('hidden.bs.modal', function() {
        var provSel = document.getElementById('agentProviderSelect');
        if (provSel) provSel.disabled = false;
        var authenticated = !!(window.agentCredentialsInMemory || window.agentCredentialsFromKey);
        if (!authenticated) self.revertPendingMode();
        self._updateStatus();
      });
    },

    revertPendingMode: function() {
      this.llmMode = this._prevMode || 'off';
      this.renderSwitch();
      this._callbacks.syncMultiAgent(false);
      if (this.llmMode !== 'off') {
        this._callbacks.setProvider(this.llmMode, false);
      }
    },

    onProfileAppliedSuccess: function() {
      this._prevMode = this.llmMode;
      if (!this.flowPlan || !this.flowPlan.steps) {
        this._callbacks.refreshUi();
        this._updateStatus();
        return;
      }
      var nextIdx = this._stepIndex + 1;
      while (nextIdx < this.flowPlan.steps.length && this.flowPlan.steps[nextIdx].kind !== 'profile') {
        nextIdx++;
      }
      if (nextIdx < this.flowPlan.steps.length && this.flowPlan.steps[nextIdx].kind === 'profile') {
        this._stepIndex = nextIdx;
        var self = this;
        setTimeout(function() { self._runCurrentStep(); }, 400);
      } else {
        this._callbacks.refreshUi();
      }
      this._updateStatus();
    },

    openSingleProfileModal: function(provider) {
      var self = this;
      this.fetchFlowPlan(provider).then(function(plan) {
        self.flowPlan = plan;
        self._stepIndex = 0;
        self._runCurrentStep();
      });
    },

    startProfileWizard: function(providerIds, modelsByProvider) {
      var self = this;
      this.saveMultiActiveProviders(providerIds, modelsByProvider || {});
      this.fetchFlowPlan('multi', { selected_provider_ids: providerIds }).then(function(plan) {
        self.flowPlan = plan;
        self._stepIndex = 0;
        for (var i = 0; i < plan.steps.length; i++) {
          if (plan.steps[i].kind === 'profile') { self._stepIndex = i; break; }
        }
        self._runCurrentStep();
      });
    },

    _updateStatus: function() {
      if (!this._statusEl) return;
      if (this.llmMode !== 'off') {
        this._statusEl.textContent = this.llmMode + ' · единый flow profile';
      } else {
        this._statusEl.textContent = 'LLM не выбран';
      }
    },

    hasPendingProfileSteps: function() {
      if (!this.flowPlan || !this.flowPlan.steps) return false;
      for (var i = this._stepIndex + 1; i < this.flowPlan.steps.length; i++) {
        if (this.flowPlan.steps[i].kind === 'profile') return true;
      }
      return false;
    }
  };
})(window);
