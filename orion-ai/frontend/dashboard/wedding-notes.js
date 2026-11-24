function afficherNotesWedding(container, tasks, request, workflow, lireApi) {
  const categories = {
    decision:'Décision', meeting:'Compte rendu', document:'Référence documentaire', idea:'Idée',
  };
  const taskTitles = new Map(tasks.map(task => [task.id, task.titre]));
  const node = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const field = (label, input) => {
    const wrapper = node('label', label);
    wrapper.append(input);
    return wrapper;
  };
  const selectCategory = () => {
    const select = node('select');
    for (const [id, title] of Object.entries(categories)) select.add(new Option(title, id));
    return select;
  };
  const section = node('details');
  section.append(node('summary', 'Mémoire du dossier'));
  container.replaceChildren(section);

  const search = node('form');
  search.className = 'workflow-form filters';
  const query = node('input');
  query.type = 'search';
  query.maxLength = 250;
  const filter = selectCategory();
  filter.add(new Option('Toutes', '', true, true), 0);
  search.append(field('Rechercher dans les notes', query), field('Catégorie', filter), node('button', 'Rechercher'));
  const editor = node('form');
  editor.className = 'workflow-form';
  const title = node('input');
  title.required = true;
  title.maxLength = 180;
  const category = selectCategory();
  const content = node('textarea');
  content.required = true;
  content.maxLength = 16000;
  const source = node('input');
  source.maxLength = 1000;
  const related = node('select');
  related.add(new Option('Aucune', ''));
  for (const [id, name] of taskTitles) related.add(new Option(name, id));
  const save = node('button', 'Ajouter la note');
  const cancel = node('button', 'Annuler la modification');
  cancel.type = 'button';
  cancel.hidden = true;
  editor.append(field('Titre', title), field('Catégorie de la note', category),
    field('Contenu', content), field('Source, lien ou nom du fichier', source),
    field('Tâche liée', related), save, cancel);
  const status = node('p');
  status.setAttribute('role', 'status');
  const results = node('div');
  const paging = node('div');
  section.append(search, status, results, paging, editor);
  const dates = new Intl.DateTimeFormat('fr-FR', {
    dateStyle:'medium', timeStyle:'short', timeZone:'Europe/Paris',
  });
  const selected = new Map();
  const studio = node('section');
  studio.className = 'wedding-source-workflow';
  const form = node('form');
  form.className = 'workflow-form';
  const template = node('select');
  template.required = true;
  const brief = node('textarea');
  brief.maxLength = 3000;
  brief.placeholder = 'Précisez le livrable attendu et les points à vérifier.';
  const sources = node('ol');
  const run = node('button', 'Exécuter avec ces sources');
  run.disabled = true;
  const history = node('select');
  const openRun = node('button', 'Consulter');
  openRun.type = 'button';
  openRun.disabled = true;
  const historyBar = node('div');
  historyBar.className = 'filters';
  historyBar.append(field('Exécutions récentes', history), openRun);
  const output = node('div');
  output.setAttribute('aria-live', 'polite');
  form.append(field('Modèle Wedding', template), field('Brief complémentaire', brief), sources, run);
  studio.append(node('h3', 'Workflow avec sources'), form, historyBar, output);
  section.append(studio);

  function refreshSources() {
    sources.replaceChildren();
    if (!selected.size) sources.append(node('li', 'Sélectionnez des notes dans les résultats.'));
    for (const [id, note] of selected) {
      const row = node('li', note.title + ' ');
      const remove = node('button', 'Retirer');
      remove.type = 'button';
      remove.onclick = () => {
        selected.delete(id);
        refreshSources();
      };
      row.append(remove);
      sources.append(row);
    }
    for (const input of results.querySelectorAll('[data-source-id]')) {
      input.checked = selected.has(input.dataset.sourceId);
      input.disabled = !input.checked && selected.size >= 5;
    }
    run.disabled = !selected.size || !template.value;
  }

  async function loadHistory() {
    const runs = await workflow('');
    history.disabled = false;
    history.replaceChildren();
    history.add(new Option('Sélectionner une exécution', ''));
    for (const item of runs) {
      const date = dates.format(new Date(item.created_at.replace(' ', 'T') + 'Z'));
      const state = {completed:'Terminée', failed:'Interrompue', running:'En cours'}[item.status];
      history.add(new Option(date + ' · ' + (state || item.status), item.id));
    }
    openRun.disabled = true;
  }

  function renderRun(result) {
    const state = {completed:'Workflow terminé', failed:'Workflow interrompu', running:'Workflow en cours'};
    output.replaceChildren(node('h4', state[result.status] || result.status));
    if (result.error) output.append(node('p', result.error));
    const mission = node('details');
    mission.append(node('summary', 'Mission exécutée'), node('pre', result.task));
    output.append(mission);
    const manifest = node('details');
    manifest.append(node('summary', 'Sources transmises'));
    result.sources.forEach((note, index) => {
      const row = node('details');
      row.append(node('summary', '[S' + (index + 1) + '] ' + note.title),
        node('p', dates.format(new Date(note.updated_at)) + (note.source ? ' · ' + note.source : '')),
        node('pre', note.content));
      manifest.append(row);
    });
    output.append(manifest);
    for (const step of result.steps) {
      output.append(node('h4', step.agent + ' · ' + step.mode),
        node('pre', step.result ?? 'Résultat non conservé.'));
    }
  }

  history.onchange = () => { openRun.disabled = !history.value; };
  openRun.onclick = async () => {
    openRun.disabled = true;
    try {
      renderRun(await workflow('/' + history.value));
    } catch (error) { output.textContent = error.message; }
    finally { openRun.disabled = !history.value; }
  };
  template.onchange = refreshSources;
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = {template_id:template.value, brief:brief.value, note_ids:[...selected.keys()]};
    if (!payload.note_ids.length) return;
    const controls = [...form.elements];
    const disabled = controls.map(control => control.disabled);
    controls.forEach(control => { control.disabled = true; });
    output.textContent = 'Exécution en cours…';
    try {
      renderRun(await workflow('', 'POST', payload));
      await loadHistory().catch(() => { history.disabled = true; });
    } catch (error) { output.textContent = error.message; }
    finally {
      controls.forEach((control, index) => { control.disabled = disabled[index]; });
      refreshSources();
    }
  };

  const limit = 20;
  let offset = 0;
  let filters = {q:'', kind:''};
  let editing;
  let revision = 0;

  function resetEditor() {
    editing = undefined;
    editor.reset();
    save.textContent = 'Ajouter la note';
    cancel.hidden = true;
  }
  cancel.onclick = resetEditor;

  async function load() {
    const number = ++revision;
    const params = new URLSearchParams({q:filters.q, offset, limit});
    if (filters.kind) params.set('kind', filters.kind);
    try {
      const data = await request('?' + params);
      if (number !== revision) return;
      status.textContent = data.notes.length ? '' : 'Aucune note trouvée.';
      results.replaceChildren();
      paging.replaceChildren();
      for (const note of data.notes) {
        if (selected.has(note.id)) selected.set(note.id, note);
        const item = node('article');
        item.className = 'wedding-record';
        const details = node('details');
        details.append(node('summary', note.title), node('p', [
          categories[note.kind], dates.format(new Date(note.updated_at)), taskTitles.get(note.task_id),
        ].filter(Boolean).join(' · ')), node('pre', note.content));
        if (note.source) details.append(node('p', 'Source · ' + note.source));
        const edit = node('button', 'Modifier');
        edit.type = 'button';
        edit.onclick = () => {
          editing = note.id;
          title.value = note.title;
          category.value = note.kind;
          content.value = note.content;
          source.value = note.source;
          related.value = note.task_id ?? '';
          save.textContent = 'Enregistrer la modification';
          cancel.hidden = false;
          title.focus();
        };
        details.append(edit);
        const use = node('input');
        use.type = 'checkbox';
        use.dataset.sourceId = note.id;
        use.onchange = () => {
          if (use.checked) selected.set(note.id, note);
          else selected.delete(note.id);
          refreshSources();
        };
        item.append(field('Utiliser comme source', use));
        item.append(details);
        results.append(item);
      }
      for (const [label, step, available] of [['Précédent', -limit, offset > 0],
                                              ['Suivant', limit, data.has_more]]) {
        const button = node('button', label);
        button.type = 'button';
        button.disabled = !available;
        button.onclick = () => {
          offset += step;
          load();
        };
        paging.append(button);
      }
      refreshSources();
      for (const button of paging.querySelectorAll('button')) button.hidden = !offset && !data.has_more;
    } catch (error) {
      if (number === revision) status.textContent = error.message;
    }
  }

  search.onsubmit = event => {
    event.preventDefault();
    filters = {q:query.value, kind:filter.value};
    offset = 0;
    load();
  };
  editor.onsubmit = async event => {
    event.preventDefault();
    save.disabled = true;
    try {
      await request(editing ? '/' + editing : '', editing ? 'PUT' : 'POST', {
        title:title.value.trim(), kind:category.value, content:content.value.trim(),
        source:source.value.trim(), task_id:related.value ? Number(related.value) : null,
      });
      resetEditor();
      filters = {q:'', kind:''};
      search.reset();
      offset = 0;
      await load();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      save.disabled = false;
    }
  };
  section.addEventListener('toggle', () => {
    if (!section.open || revision !== 0) return;
    load();
    refreshSources();
    lireApi('/wedding').then(templates => {
      for (const model of templates) template.add(new Option(model.title, model.id));
      refreshSources();
    }).catch(error => { output.textContent = error.message; });
    loadHistory().catch(error => { output.textContent = error.message; });
  });
}
