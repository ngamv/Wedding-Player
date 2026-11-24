async function afficherSites(container, preferred, preferredIntervention) {
  const root = document.createElement('div');
  root.className = 'site-operations';
  container.replaceChildren(root);
  const el = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const label = (text, input) => {
    const field = el('label', text);
    field.append(input);
    return field;
  };
  const button = (text, action) => {
    const control = el('button', text);
    control.type = 'button';
    control.onclick = action;
    return control;
  };
  async function request(path = '', method = 'GET', data) {
    const response = await fetch('/api/sites' + path, {
      method, cache:'no-store',
      ...(data === undefined ? {} : {headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Vérifiez les champs saisis.');
    return result;
  }
  const status = el('p', 'Chargement du registre…');
  status.setAttribute('role', 'status');
  root.append(status);
  let data;
  try { data = await request(); }
  catch (error) {
    status.textContent = error instanceof SyntaxError ? 'Le registre des sites nécessite le serveur ORION local.' : error.message;
    return;
  }

  const state = {
    draft:'À valider', approved:'Validée', rejected:'Plan écarté', verified:'Résultat vérifié',
    simulation:'Simulation', failed:'Échec du workflow',
  };
  const active = el('select');
  const registry = el('section');
  registry.className = 'panel site-registry';
  const summary = el('div');
  const form = el('form');
  form.className = 'workflow-form';
  const fields = [
    ['name','Nom du site','text',140,true], ['url','Adresse du site','url',2083,true],
    ['platform','CMS ou hébergeur','text',140,false], ['repo','Dépôt GitHub public (organisation/dépôt)','text',140,false],
    ['objective','Objectif du site','text',1000,false],
  ];
  for (const [key, caption, type, max, required] of fields) {
    const input = el('input');
    Object.assign(input, {name:key, type, maxLength:max, required});
    form.append(label(caption, input));
  }
  const save = el('button', 'Enregistrer le site');
  form.append(save);
  registry.append(el('h2', 'Raccordement'), label('Site à piloter', active), form, summary);

  const studio = el('section');
  studio.className = 'panel site-studio';
  const mission = el('form');
  mission.className = 'workflow-form';
  const template = el('select');
  const templateTitles = new Map();
  for (const entry of data.templates) {
    templateTitles.set(entry.id, entry.title);
    template.add(new Option(entry.title, entry.id));
  }
  const brief = el('textarea');
  Object.assign(brief, {required:true, maxLength:3000, placeholder:'Objectif, pages concernées et constats à vérifier'});
  const launch = el('button', 'Préparer l’intervention');
  mission.append(label('Workflow', template), label('Brief', brief), launch);
  const history = el('div');
  const detail = el('div');
  detail.setAttribute('aria-live', 'polite');
  studio.append(el('h2', 'Interventions'), el('p', data.mode === 'ollama' ? 'Moteur local · Ollama' : 'Moteur local · Simulation'),
    mission, el('h3', 'Journal des interventions'), history, detail);
  const grid = el('div');
  grid.className = 'site-grid';
  grid.append(registry, studio);
  root.append(grid);

  let revision = 0;
  const getSite = () => data.sites.find(site => site.id === active.value);
  function options(id) {
    active.replaceChildren();
    active.add(new Option('Ajouter un site', ''));
    for (const site of data.sites) active.add(new Option(site.name, site.id));
    active.value = id;
  }

  async function renderHistory(id) {
    const sequence = ++revision;
    history.replaceChildren();
    if (!id) { history.append(el('p','Enregistrez un site pour préparer une intervention.')); return; }
    const rows = await request('/' + id + '/interventions');
    if (sequence !== revision) return;
    if (!rows.length) history.append(el('p','Aucune intervention enregistrée.'));
    for (const item of rows) {
      const row = el('div');
      row.className = 'item';
      const status = el('span', state[item.state]);
      status.className = 'pill';
      row.append(button(templateTitles.get(item.template) || item.template, async () => {
        try {
          const result = await request('/' + id + '/interventions/' + item.id);
          if (active.value === id) renderIntervention(id, result);
        } catch (error) { detail.textContent = error.message; }
      }), status);
      history.append(row);
    }
  }

  function renderIntervention(id, {intervention, run}) {
    detail.replaceChildren(el('h3', templateTitles.get(intervention.template)), el('p', state[intervention.state]));
    if (run?.error) detail.append(el('p', run.error));
    for (const step of run?.steps ?? []) {
      const stage = el('details');
      stage.append(el('summary', step.agent), el('pre', step.result ?? 'Résultat non conservé.'));
      detail.append(stage);
    }
    if (intervention.result) detail.append(el('p',
      intervention.state === 'rejected' ? 'Motif · ' + intervention.result : intervention.result));
    async function advance(action, result, control) {
      control.disabled = true;
      try {
        const changed = await request('/' + id + '/interventions/' + intervention.id, 'PATCH', {action,result});
        if (active.value !== id) return;
        renderIntervention(id, {intervention:changed, run});
        await renderHistory(id);
      } catch (error) { status.textContent = error.message; }
      finally { control.disabled = false; }
    }
    if (intervention.state === 'draft') {
      const approve = button('Valider le plan', () => advance('approve', '', approve));
      const decline = el('details');
      const form = el('form');
      form.className = 'workflow-form';
      const reason = el('textarea');
      Object.assign(reason, {required:true,maxLength:2000});
      const submit = el('button', 'Enregistrer le refus');
      form.append(label('Motif du refus', reason), submit);
      form.onsubmit = event => {
        event.preventDefault();
        advance('reject', reason.value, submit);
      };
      decline.append(el('summary', 'Écarter ce plan'), form);
      detail.append(approve, decline);
    }
    if (intervention.state === 'approved') {
      const check = el('form');
      check.className = 'workflow-form';
      const result = el('textarea');
      Object.assign(result, {required:true,maxLength:2000});
      const submit = el('button','Consigner le résultat');
      check.append(label('Action réalisée et résultat du contrôle', result), submit);
      check.onsubmit = event => {
        event.preventDefault();
        advance('verify', result.value, submit);
      };
      detail.append(check);
    }
  }

  async function select() {
    const site = getSite();
    for (const [key] of fields) form.elements[key].value = site?.[key] ?? '';
    launch.disabled = !site;
    detail.replaceChildren();
    summary.replaceChildren();
    if (site) {
      const link = el('a', 'Ouvrir le site');
      Object.assign(link, {href:site.url, target:'_blank', rel:'noopener noreferrer'});
      const sync = button('Synchroniser GitHub', async () => {
        sync.disabled = true;
        try {
          const changed = await request('/' + site.id + '/github', 'POST');
          data.sites = data.sites.map(item => item.id === changed.id ? changed : item);
          if (active.value === site.id) await select();
        } catch (error) { status.textContent = error.message; }
        finally { sync.disabled = !site.repo; }
      });
      sync.disabled = !site.repo;
      summary.append(link, sync);
      if (site.github) {
        summary.append(el('p', [
          site.github.full_name, 'branche ' + site.github.default_branch,
          'Synchronisé le ' + new Date(site.synced_at.replace(' ', 'T') + 'Z').toLocaleString('fr-FR'),
        ].join(' · ')));
      }
    }
    try { await renderHistory(site?.id); }
    catch (error) { status.textContent = error.message; }
  }

  form.onsubmit = async event => {
    event.preventDefault();
    const id = active.value;
    save.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      const site = await request(id ? '/' + id : '', id ? 'PUT' : 'POST', values);
      data.sites = [...data.sites.filter(item => item.id !== site.id), site].sort((a,b) => a.name.localeCompare(b.name));
      options(site.id);
      status.textContent = 'Site enregistré.';
      await select();
    } catch (error) { status.textContent = error.message; }
    finally { save.disabled = false; }
  };
  mission.onsubmit = async event => {
    event.preventDefault();
    const id = active.value;
    if (!id) return;
    launch.disabled = true;
    detail.textContent = 'Workflow en cours…';
    try {
      const result = await request('/' + id + '/interventions', 'POST', {template:template.value, brief:brief.value});
      if (active.value !== id) return;
      renderIntervention(id, result);
      await renderHistory(id);
    } catch (error) { if (active.value === id) detail.textContent = error.message; }
    finally { launch.disabled = !active.value; }
  };
  active.onchange = select;
  options(data.sites.some(site => site.id === preferred) ? preferred : (data.sites[0]?.id ?? ''));
  status.textContent = '';
  await select();
  if (active.value === preferred && preferredIntervention && /^[a-f0-9]{32}$/.test(preferredIntervention)) {
    try {
      const result = await request('/' + preferred + '/interventions/' + preferredIntervention);
      if (active.value === preferred) {
        renderIntervention(preferred, result);
        detail.scrollIntoView({block:'nearest'});
      }
    } catch (error) {
      detail.textContent = error.message;
    }
  }
}
