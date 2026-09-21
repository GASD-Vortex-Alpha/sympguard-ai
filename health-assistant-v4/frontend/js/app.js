/**
 * SympGuard AI -- symptom-checker app flow.
 * Plain JS state machine, no framework. Views are toggled via .active class.
 */
(function () {
  var state = {
    sessionId: null,
    region: (window.SYMPGUARD_CONFIG && window.SYMPGUARD_CONFIG.DEFAULT_REGION) || null,
    currentQuestions: [],
    currentAnswers: {},
    lastRetry: null,
  };

  function $(id) { return document.getElementById(id); }
  function escapeHtml(s) { var d = document.createElement('div'); d.textContent = (s == null ? '' : s); return d.innerHTML; }

  function showView(id) {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.remove('active'); });
    $(id).classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setStep(n) {
    for (var i = 1; i <= 3; i++) {
      var el = $('step-' + i);
      el.className = i < n ? 'done' : (i === n ? 'active' : '');
    }
  }

  function setLoading(message) {
    $('loading-message').textContent = message;
    showView('view-loading');
  }

  function setError(title, message, retryFn) {
    $('error-title').textContent = title;
    $('error-message').textContent = message;
    state.lastRetry = retryFn;
    showView('view-error');
  }

  // ---------------- STEP 1: symptom input ----------------

  var textarea = $('symptom-text');
  textarea.addEventListener('input', function () {
    $('char-count').textContent = String(textarea.value.length);
  });

  $('start-btn').addEventListener('click', function () {
    var text = textarea.value.trim();
    if (text.length < 3) {
      $('input-error').style.display = '';
      return;
    }
    $('input-error').style.display = 'none';
    startCheck(text);
  });

  function startCheck(text) {
    setStep(1);
    setLoading('Reviewing what you told us…');
    SympGuardAPI.startCheck(text, state.region).then(function (data) {
      state.sessionId = data.session_id;
      state.extractedSymptoms = data.extracted_symptoms;
      if (data.done) {
        runAnalysis();
      } else {
        setStep(2);
        renderQuestionBatch(data.questions);
      }
    }).catch(function (err) {
      setError('Could not start your symptom check', err.message, function () { startCheck(text); });
    });
  }

  // ---------------- STEP 2: adaptive questions ----------------

  function renderQuestionBatch(questions) {
    state.currentQuestions = questions;
    state.currentAnswers = {};
    var card = $('question-card');
    card.innerHTML = '';

    questions.forEach(function (q, idx) {
      var wrap = document.createElement('div');
      wrap.style.marginBottom = idx < questions.length - 1 ? '2rem' : '0';
      var meta = document.createElement('div');
      meta.className = 'question-meta';
      meta.textContent = 'Question ' + (idx + 1) + ' of ' + questions.length;
      var h = document.createElement('h2');
      h.textContent = q.prompt;
      var optionsWrap = document.createElement('div');
      optionsWrap.className = 'option-group';
      optionsWrap.setAttribute('role', 'group');
      optionsWrap.setAttribute('aria-label', q.prompt);

      var options = q.type === 'yes_no' ? ['Yes', 'No'] : (q.options || []);
      options.forEach(function (opt) {
        var btn = document.createElement('button');
        btn.className = 'option-btn';
        btn.type = 'button';
        btn.textContent = opt;
        btn.setAttribute('aria-pressed', 'false');
        btn.addEventListener('click', function () {
          optionsWrap.querySelectorAll('.option-btn').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
          btn.setAttribute('aria-pressed', 'true');
          state.currentAnswers[q.id] = opt;
          updateContinueButton();
        });
        optionsWrap.appendChild(btn);
      });

      wrap.appendChild(meta);
      wrap.appendChild(h);
      wrap.appendChild(optionsWrap);
      card.appendChild(wrap);
    });

    var continueBtn = document.createElement('button');
    continueBtn.className = 'btn btn-primary btn-lg btn-block';
    continueBtn.id = 'questions-continue-btn';
    continueBtn.textContent = 'Continue';
    continueBtn.disabled = true;
    continueBtn.style.marginTop = 'var(--space-5)';
    continueBtn.addEventListener('click', submitAnswers);
    card.appendChild(continueBtn);

    card.appendChild(renderAddDetailsToggle());

    showView('view-questions');
  }

  function renderAddDetailsToggle() {
    var wrap = document.createElement('div');
    wrap.className = 'add-details-wrap';

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'add-details-toggle';
    toggle.textContent = 'Something else going on? Type it here';

    var panel = document.createElement('div');
    panel.className = 'add-details-panel';
    panel.style.display = 'none';
    panel.innerHTML =
      '<textarea id="add-details-text" rows="2" placeholder="e.g. I also noticed a rash on my arm, or: I forgot to mention I have a fever too" maxlength="500"></textarea>' +
      '<button type="button" class="btn btn-secondary" id="add-details-submit">Add to my symptom check</button>' +
      '<p class="faint" id="add-details-status" style="margin:0.5em 0 0;"></p>';

    toggle.addEventListener('click', function () {
      var open = panel.style.display !== 'none';
      panel.style.display = open ? 'none' : '';
    });

    wrap.appendChild(toggle);
    wrap.appendChild(panel);

    // Deferred so the elements exist in the DOM before wiring the handler
    setTimeout(function () {
      var submitBtn = document.getElementById('add-details-submit');
      if (submitBtn) submitBtn.addEventListener('click', submitAddDetails);
    }, 0);

    return wrap;
  }

  function submitAddDetails() {
    var textarea = document.getElementById('add-details-text');
    var status = document.getElementById('add-details-status');
    var text = textarea.value.trim();
    if (text.length < 3) {
      status.textContent = 'Add a few more words describing what you noticed.';
      return;
    }
    var submitBtn = document.getElementById('add-details-submit');
    submitBtn.disabled = true;
    status.textContent = 'Adding…';

    SympGuardAPI.addDetails(state.sessionId, text).then(function (data) {
      if (data.done) {
        runAnalysis();
        return;
      }
      setStep(2);
      renderQuestionBatch(data.questions);
    }).catch(function (err) {
      submitBtn.disabled = false;
      status.textContent = 'Could not add that: ' + err.message;
    });
  }

  function updateContinueButton() {
    var allAnswered = state.currentQuestions.every(function (q) { return state.currentAnswers[q.id] !== undefined; });
    var btn = $('questions-continue-btn');
    if (btn) btn.disabled = !allAnswered;
  }

  function submitAnswers() {
    var answers = Object.keys(state.currentAnswers).map(function (qid) {
      return { question_id: qid, answer: state.currentAnswers[qid] };
    });
    setLoading('Thinking about what to ask next…');
    SympGuardAPI.followUp(state.sessionId, answers).then(function (data) {
      if (data.done) {
        runAnalysis();
      } else {
        setStep(2);
        renderQuestionBatch(data.questions);
      }
    }).catch(function (err) {
      setError('Could not submit your answers', err.message, submitAnswers);
    });
  }

  // ---------------- STEP 3: analysis + results ----------------

  function runAnalysis() {
    setStep(3);
    setLoading('Running safety checks and building your results…');
    SympGuardAPI.analyze(state.sessionId).then(function (data) {
      renderResults(data);
    }).catch(function (err) {
      setError('Could not complete your analysis', err.message, runAnalysis);
    });
  }

  function triageBadgeClass(category) {
    return { EMERGENCY: 'badge-emergency', URGENT_MEDICAL_EVALUATION: 'badge-urgent',
      ROUTINE_MEDICAL_CONSULTATION: 'badge-routine', SELF_CARE_MONITORING: 'badge-selfcare' }[category] || 'badge-routine';
  }

  function renderResults(data) {
    state.lastResult = data;
    var root = $('view-results');
    var html = '';

    if (data.is_emergency) {
      html += renderEmergencyBanner(data);
    }

    html += '<div class="row" style="justify-content:space-between;align-items:center;">' +
      '<h1 style="margin:0;">Your Results</h1>' +
      '<span class="badge ' + triageBadgeClass(data.triage.category) + '">' + escapeHtml(data.triage.label) + '</span>' +
      '</div>';

    html += section('Urgency', '<p style="margin:0;">' + escapeHtml(data.triage.reasoning) + '</p>');
    html += section('Why This Was Flagged', '<p style="margin:0;">' + escapeHtml(data.why_flagged) + '</p>');

    html += section('Possible Explanations', renderMatches(data.possible_explanations) +
      '<hr class="divider"><p class="faint" style="margin:0;">' + escapeHtml(data.explanation.text) + '</p>' +
      (data.explanation.source === 'deterministic_fallback' ? '<p class="faint" style="margin-top:var(--space-2);">🛈 Generated by SympGuard AI\'s built-in explanation engine (no AI API key configured — DEMO_MODE).</p>' : ''));

    html += section('What You Told Us', renderWhatYouToldUs(data.what_you_told_us));

    html += section('Red Flags Checked', renderRedFlags(data.red_flags_checked));

    html += section('Evidence', renderEvidence(data.evidence));

    if (data.first_aid_suggestions && data.first_aid_suggestions.length) {
      html += section('First Aid', renderFirstAidSuggestions(data.first_aid_suggestions));
    }

    html += section('What To Do Next', '<p style="margin:0;">' + escapeHtml(data.what_to_do_next) + '</p>');
    html += section('When To Seek Professional Care', '<p style="margin:0;">' + escapeHtml(data.when_to_seek_care) + '</p>');

    html += section('Doctor-Ready Summary', '<p class="muted">Create a structured summary of this check to bring to a clinician.</p>' +
      '<button class="btn btn-primary" id="create-summary-btn">Create Doctor Summary</button>');

    html += section('Uncertainty &amp; Limitations', '<p style="margin:0;" class="muted">' + escapeHtml(data.uncertainty_limitations) + '</p>');

    html += '<div class="row" style="margin-top:var(--space-6);">' +
      '<button class="btn btn-secondary" id="restart-btn">Start a new check</button>' +
      '</div>';

    html += '<p class="foot-disclaimer" style="margin-top:var(--space-7);">' + escapeHtml(data.disclaimer) + '</p>';

    root.innerHTML = html;
    $('create-summary-btn').addEventListener('click', openDoctorSummary);
    $('restart-btn').addEventListener('click', restart);
    showView('view-results');
  }

  function section(title, bodyHtml) {
    return '<div class="result-section"><h3>' + escapeHtml(title) + '</h3><div class="card">' + bodyHtml + '</div></div>';
  }

  function renderEmergencyBanner(data) {
    var contacts = data.emergency_contacts;
    var callButtons = '';
    if (contacts) {
      contacts.general.forEach(function (c) {
        callButtons += '<a class="btn btn-emergency btn-lg" href="tel:' + encodeURIComponent(c.number) + '">Call ' + escapeHtml(c.number) + ' — ' + escapeHtml(c.name) + '</a>';
      });
      contacts.mental_health_crisis.forEach(function (c) {
        callButtons += '<a class="btn btn-secondary btn-lg" href="tel:' + encodeURIComponent(c.number) + '">Call ' + escapeHtml(c.number) + ' — ' + escapeHtml(c.name) + '</a>';
      });
    }
    return '<div class="emergency-banner">' +
      '<h2>Possible Medical Emergency</h2>' +
      '<p style="margin:0;">Your answers contain symptoms that may require immediate professional assessment.</p>' +
      '<div class="call-row">' + callButtons + '<a class="btn btn-secondary btn-lg" href="first-aid.html">View First Aid</a></div>' +
      '<p class="faint" style="margin-top:var(--space-4);margin-bottom:0;">If you believe you are in immediate danger, contact emergency services now. This app cannot dispatch help.</p>' +
      '</div>';
  }

  function renderMatches(matches) {
    if (!matches.length) return '<p class="muted" style="margin:0;">No confident match was found against the knowledge base.</p>';
    return matches.map(function (m) {
      return '<div class="match-item">' +
        '<div class="match-head"><strong>' + escapeHtml(m.name) + '</strong><span class="confidence">confidence ' + m.confidence + '</span></div>' +
        '<p class="muted" style="margin:0.4em 0;">' + escapeHtml(m.description) + '</p>' +
        m.matched_symptoms.map(function (s) { return '<span class="chip">' + escapeHtml(s) + '</span>'; }).join('') +
        '</div>';
    }).join('');
  }

  function renderWhatYouToldUs(w) {
    var html = '<p><strong>You said:</strong> "' + escapeHtml(w.original_description) + '"</p>';
    html += '<p><strong>Symptoms identified:</strong> ' + (w.extracted_symptoms.length ? w.extracted_symptoms.map(escapeHtml).join(', ') : 'none confidently identified') + '</p>';
    if (w.answers.length) {
      html += '<ul class="qa-list">' + w.answers.map(function (qa) {
        return '<li><div class="q">' + escapeHtml(qa.question) + '</div><div class="a">' + escapeHtml(qa.answer) + '</div></li>';
      }).join('') + '</ul>';
    }
    return html;
  }

  function renderRedFlags(safety) {
    if (!safety.is_emergency) {
      return '<p style="margin:0;" class="muted">No emergency red flags were detected by the independent safety check.</p>';
    }
    var html = '<p style="margin:0 0 0.6em;"><strong>Matched phrases:</strong> ' + (safety.matched_phrases.length ? safety.matched_phrases.map(escapeHtml).join(', ') : 'none') + '</p>';
    if (safety.matched_combinations.length) {
      html += '<p style="margin:0;"><strong>Matched patterns:</strong> ' + safety.matched_combinations.map(function (c) { return escapeHtml(c.label); }).join(', ') + '</p>';
    }
    return html;
  }

  function renderEvidence(evidence) {
    if (!evidence.length) return '<p class="muted" style="margin:0;">No matched conditions to show evidence for.</p>';
    return evidence.map(function (e) {
      return '<div class="evidence-item"><strong>' + escapeHtml(e.condition_name) + '</strong>' +
        '<p class="muted" style="margin:0.4em 0;">Matched on: ' + e.matched_on.map(escapeHtml).join(', ') + '</p>' +
        '<p class="evidence-disclosure">' + escapeHtml(e.source_disclosure) + ' General references for further reading: ' + e.general_reference_suggestions.map(escapeHtml).join(', ') + '.</p>' +
        '</div>';
    }).join('');
  }

  function renderFirstAidSuggestions(topics) {
    return '<div class="fa-suggest-grid">' + topics.map(function (t) {
      return '<a class="btn btn-secondary" href="first-aid.html#' + encodeURIComponent(t.id) + '">' + escapeHtml(t.topic) + '</a>';
    }).join('') + '</div>';
  }

  // ---------------- Doctor summary modal ----------------

  function openDoctorSummary() {
    var btn = $('create-summary-btn');
    btn.disabled = true;
    btn.textContent = 'Creating…';
    SympGuardAPI.doctorSummary(state.sessionId).then(function (summary) {
      state.doctorSummaryText = summary.plain_text;
      $('doctor-summary-text').textContent = summary.plain_text;
      $('doctor-summary-modal').classList.add('open');
    }).catch(function (err) {
      alert('Could not create the doctor summary: ' + err.message);
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = 'Create Doctor Summary';
    });
  }

  $('close-summary-btn').addEventListener('click', function () { $('doctor-summary-modal').classList.remove('open'); });
  $('copy-summary-btn').addEventListener('click', function () {
    navigator.clipboard.writeText(state.doctorSummaryText || '').then(function () {
      var btn = $('copy-summary-btn');
      var original = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(function () { btn.textContent = original; }, 1500);
    }).catch(function () { alert('Could not copy automatically -- please select and copy the text manually.'); });
  });
  $('print-summary-btn').addEventListener('click', function () { window.print(); });

  // ---------------- error view + restart ----------------

  $('error-retry-btn').addEventListener('click', function () {
    if (state.lastRetry) state.lastRetry();
  });
  $('error-restart-btn').addEventListener('click', restart);

  function restart() {
    state.sessionId = null;
    state.currentQuestions = [];
    state.currentAnswers = {};
    textarea.value = '';
    $('char-count').textContent = '0';
    $('input-error').style.display = 'none';
    setStep(1);
    showView('view-input');
  }

  document.getElementById('nav-toggle').addEventListener('click', function () {
    var nav = document.getElementById('main-nav');
    var open = nav.classList.toggle('open');
    this.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
})();
