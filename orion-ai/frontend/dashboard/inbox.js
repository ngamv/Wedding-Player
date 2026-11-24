async function afficherInbox(container, preferred, project) {
  const root = document.createElement('div');
  root.className = 'inbox-grid';
  root.innerHTML = [
    '<section class="panel"><h2>Capturer un élément</h2>',
    '<form data-capture class="workflow-form">',
    '<label>Titre<input name="title" required maxlength="180"></label>',
    '<div class="filters"><label>Type<select name="kind" required></select></label>',
    '<label>Dossier associé<select name="target"></select></label></div>',
    '<label>Importer un fichier<input type="file" name="file" accept=".txt,.md,.vtt,.srt,.csv,.pdf,.jpg,.jpeg,.wav,.mp3,.m4a,.ogg,.flac"></label>',
    '<label>Contenu<textarea name="content" required maxlength="50000" rows="7"></textarea></label>',
    '<label>Source ou référence<input name="source" maxlength="1000"></label>',
    '<div class="filters"><label>Date de la source<input name="source_date" type="date"></label>',
    '<label>Échéance<input name="due_date" type="date"></label></div>',
    '<div class="filters"><button type="submit">Enregistrer</button>',
    '<button type="button" data-reset hidden>Annuler la modification</button></div></form>',
    '<p role="status" data-capture-status></p></section>',
    '<section class="panel"><div class="inbox-header"><h2>Boîte de réception</h2>',
    '<button type="button" data-export>Exporter JSON</button></div>',
    '<form class="workflow-form" data-search><div class="filters">',
    '<label>Recherche<input type="search" name="q" maxlength="250"></label>',
    '<label>Type<select name="kind"></select></label>',
    '<label>Classement<select name="scope"></select></label>',
    '<button type="submit">Rechercher</button></div></form>',
    '<p role="status" data-search-status></p><div data-results></div><div class="filters" data-pages></div></section>',
    '<section class="panel inbox-question"><h2>Interroger la mémoire</h2>',
    '<form class="workflow-form" data-question>',
    '<label>Question<textarea name="question" required maxlength="1000" placeholder="Qu’a-t-on décidé pour ce client ?"></textarea></label>',
    '<p>Utilise le classement et les mots-clés renseignés dans la recherche.</p>',
    '<button type="submit">Répondre avec les sources</button></form>',
    '<div data-answer aria-live="polite"></div></section>',
  ].join('');
  const gate = document.createElement('section');
  gate.className = 'panel';
  container.replaceChildren(gate, root);
  root.hidden = true;
  const capture = root.querySelector('[data-capture]');
  const search = root.querySelector('[data-search]');
  const save = capture.querySelector('[type=submit]');
  const reset = root.querySelector('[data-reset]');
  const captureStatus = root.querySelector('[data-capture-status]');
  const searchStatus = root.querySelector('[data-search-status]');
  const results = root.querySelector('[data-results]');
  const pages = root.querySelector('[data-pages]');
  const kinds = {note:'Note', document:'Document', meeting:'Compte rendu',
    transcript:'Transcription', decision:'Décision'};
  const names = new Map();
  let editing = null;
  let pendingFile;
  let authorization;
  let projectScope = '';
  let revision = 0;
  let offset = 0;
  let filters = {};
  const limit = 20;

  const el = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  async function send(path = '', method = 'GET', data) {
    const multipart = data instanceof FormData;
    const headers = {};
    if (authorization) headers.Authorization = authorization;
    if (data !== undefined && !multipart) headers['Content-Type'] = 'application/json';
    return fetch('/api/inbox' + path, {
      method, cache:'no-store', headers,
      body:multipart || data === undefined ? data : JSON.stringify(data),
    });
  }
  async function request(path, method, data) {
    const response = await send(path, method, data);
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Vérifiez les champs saisis.');
    return result;
  }
  async function download(path, filename) {
    try {
      const response = await send(path);
      if (!response.ok) throw new Error('Téléchargement impossible.');
      const url = URL.createObjectURL(await response.blob());
      const link = el('a');
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { searchStatus.textContent = error.message; }
  }
  root.querySelector('[data-export]').onclick = () => download('/export', 'orion-memoire.json');
  search.elements.kind.add(new Option('Tous', ''));
  for (const [id, label] of Object.entries(kinds)) {
    search.elements.kind.add(new Option(label, id));
    capture.elements.kind.add(new Option(label, id));
  }
  capture.elements.target.add(new Option('À classer', ''));
  search.elements.scope.add(new Option('Tous les dossiers', ''));
  search.elements.scope.add(new Option('À classer', 'unfiled'));

  function clearEditor() {
    editing = null;
    pendingFile = undefined;
    capture.elements.file.disabled = false;
    capture.elements.content.required = true;
    capture.reset();
    capture.elements.target.value = projectScope;
    reset.hidden = true;
    save.textContent = 'Enregistrer';
  }
  reset.onclick = () => {
    clearEditor();
    captureStatus.textContent = '';
  };
  capture.elements.file.onchange = async () => {
    const [file] = capture.elements.file.files;
    pendingFile = undefined;
    capture.elements.content.required = true;
    if (!file) return;
    try {
      if (/\.(pdf|jpe?g|wav|mp3|m4a|ogg|flac)$/i.test(file.name)) {
        if (file.size > 16 * 1024 * 1024) throw new Error('Le fichier dépasse 16 Mio.');
        pendingFile = file;
        capture.elements.content.required = false;
        capture.elements.title.value ||= file.name.slice(0, 180);
        capture.elements.kind.value = /\.(wav|mp3|m4a|ogg|flac)$/i.test(file.name) ? 'transcript' : 'document';
        captureStatus.textContent = 'Le fichier sera conservé et traité localement lors de l’enregistrement.';
        return;
      }
      if (file.size > 200000 || !/\.(txt|md|vtt|srt|csv)$/i.test(file.name)) {
        throw new Error('Sélectionnez un fichier texte de 200 Ko maximum.');
      }
      const text = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer());
      if (text.length > 50000) throw new Error('Le contenu dépasse 50 000 caractères.');
      capture.elements.content.value = text;
      capture.elements.source.value ||= file.name;
      capture.elements.title.value ||= file.name.slice(0, 180);
      captureStatus.textContent = 'Texte chargé. Enregistrez pour le conserver.';
    } catch (error) { captureStatus.textContent = error.message; }
    finally { capture.elements.file.value = ''; }
  };

  function edit(item) {
    pendingFile = undefined;
    editing = item.id;
    capture.elements.file.value = '';
    capture.elements.file.disabled = true;
    capture.elements.content.required = true;
    for (const key of ['title','kind','content','source','source_date','due_date']) {
      capture.elements[key].value = item[key] ?? '';
    }
    const target = item.target_id ? item.target_kind + ':' + item.target_id : '';
    if (target && !Array.from(capture.elements.target.options).some(option => option.value === target)) {
      capture.elements.target.add(new Option('Dossier associé existant', target));
    }
    capture.elements.target.value = target;
    save.textContent = 'Enregistrer la modification';
    reset.hidden = false;
    capture.elements.title.focus();
  }

  async function load() {
    const seq = ++revision;
    searchStatus.textContent = 'Chargement…';
    const params = new URLSearchParams({limit,offset,...filters});
    try {
      const data = await request('?' + params);
      if (seq !== revision) return;
      searchStatus.textContent = data.items.length ? '' : 'Aucun élément trouvé.';
      results.replaceChildren();
      pages.replaceChildren();
      for (const item of data.items) {
        const card = el('details');
        card.className = 'inbox-item';
        const target = names.get(item.target_kind + ':' + item.target_id);
        const meta = [kinds[item.kind], target ?? 'À classer', item.source_date,
          item.due_date ? 'Échéance ' + item.due_date : ''].filter(Boolean).join(' · ');
        card.append(el('summary', item.title), el('p', meta));
        if (item.target_kind === 'project') {
          const linked = el('a', 'Ouvrir le projet');
          linked.href = '#projets?projet=' + encodeURIComponent(item.target_id);
          card.append(linked);
        }
        if (item.source) card.append(el('p', 'Source · ' + item.source));
        const action = el('button', 'Modifier ou classer');
        action.type = 'button';
        action.onclick = () => edit(item);
        card.append(el('pre', item.content), action);
        if (item.filename) {
          const file = el('button', 'Télécharger ' + item.filename);
          file.type = 'button';
          file.onclick = () => download('/' + item.id + '/attachment', item.filename);
          card.append(file);
        }
        results.append(card);
      }
      if (offset || data.has_more) {
        for (const [caption, delta, enabled] of [['Précédent', -limit, offset > 0], ['Suivant',limit,data.has_more]]) {
          const nav = el('button', caption);
          nav.type = 'button';
          nav.disabled = !enabled;
          nav.onclick = () => { offset += delta; load(); };
          pages.append(nav);
        }
      }
    } catch (error) {
      if (seq === revision) searchStatus.textContent = error.message;
    }
  }

  search.onsubmit = event => {
    event.preventDefault();
    filters = Object.fromEntries([...new FormData(search)].filter(([, value]) => value));
    offset = 0;
    load();
  };
  capture.onsubmit = async event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(capture));
    const [target_kind, target_id] = values.target.split(':');
    const payload = {
      kind:values.kind, title:values.title.trim(), content:values.content, source:values.source.trim(),
      source_date:values.source_date || null, due_date:values.due_date || null,
      target_kind:target_kind || null, target_id:target_id || null,
    };
    save.disabled = true;
    try {
      const id = editing;
      let result;
      if (pendingFile) {
        const body = new FormData();
        body.append('metadata', JSON.stringify(payload));
        body.append('file', pendingFile);
        captureStatus.textContent = 'Extraction locale en cours…';
        result = await request('/import', 'POST', body);
      } else {
        result = await request(id ? '/' + id : '', id ? 'PUT' : 'POST', payload);
      }
      clearEditor();
      captureStatus.textContent = result.warning ? 'Fichier enregistré. ' + result.warning : 'Élément enregistré.';
      search.reset();
      search.elements.scope.value = projectScope;
      filters = projectScope ? {scope:projectScope} : {};
      offset = 0;
      await load();
    } catch (error) { captureStatus.textContent = error.message; }
    finally { save.disabled = false; }
  };

  const question = root.querySelector('[data-question]');
  const answer = root.querySelector('[data-answer]');
  question.onsubmit = async event => {
    event.preventDefault();
    const submit = question.querySelector('button');
    submit.disabled = true;
    answer.textContent = 'Recherche des sources et génération…';
    try {
      const result = await request('/question', 'POST', {
        question:question.elements.question.value,
        query:search.elements.q.value,
        scope:search.elements.scope.value,
      });
      answer.replaceChildren(el('pre', result.answer));
      for (const source of result.sources) {
        const item = el('details');
        item.append(el('summary', '[' + source.reference + '] ' + source.title + ' · ' + (source.date || 'Date inconnue')),
          el('p', source.source || 'Source non renseignée'), el('pre', source.content));
        answer.append(item);
      }
    } catch (error) { answer.textContent = error.message; }
    finally { submit.disabled = false; }
  };

  async function start(session) {
    gate.replaceChildren();
    gate.hidden = !session.username;
    if (session.username) {
      const logout = el('button', 'Se déconnecter');
      logout.type = 'button';
      logout.onclick = () => {
        if (authorization) afficherInbox(container, preferred, project);
        else fermerSessionOrion().catch(error => { searchStatus.textContent = error.message; });
      };
      gate.append(el('p', 'Connecté · ' + session.username), logout);
    }
    root.hidden = false;
    for (const row of await request('/targets')) {
      const id = row.kind + ':' + row.id;
      const label = ({site:'Site', wedding:'Wedding', project:'Projet'}[row.kind]) + ' · ' + row.name;
      names.set(id, label);
      capture.elements.target.add(new Option(label, id));
      search.elements.scope.add(new Option(label, id));
    }
    const context = 'project:' + project;
    if (project && names.has(context)) {
      projectScope = context;
      capture.elements.target.value = context;
      search.elements.scope.value = context;
      filters = {scope:context};
    }
    await load();
    if (preferred && /^[a-f0-9]{32}$/.test(preferred)) {
      try { edit(await request('/' + preferred)); }
      catch (error) { searchStatus.textContent = error.message; }
    }
  }

  try {
    const response = await send('/session');
    if (response.status === 401) {
      gate.innerHTML = '<h2>Connexion à la mémoire</h2><form class="workflow-form">' +
        '<label>Compte<input name="username" autocomplete="username" required></label>' +
        '<label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label>' +
        '<button>Se connecter</button></form><p role="status"></p>';
      const login = gate.querySelector('form');
      const message = gate.querySelector('[role=status]');
      login.onsubmit = async event => {
        event.preventDefault();
        const submit = login.querySelector('button');
        submit.disabled = true;
        try {
          authorization = 'Basic ' + btoa(login.elements.username.value + ':' + login.elements.password.value);
          const session = await request('/session');
          login.reset();
          await start(session);
        } catch {
          authorization = undefined;
          message.textContent = 'Connexion impossible. Vérifiez le compte et le mot de passe.';
        } finally { submit.disabled = false; }
      };
    } else if (response.ok) {
      await start(await response.json());
    } else {
      throw new Error();
    }
  } catch {
    gate.hidden = false;
    gate.textContent = 'La boîte de réception nécessite le serveur ORION local.';
    save.disabled = true;
  }
}
