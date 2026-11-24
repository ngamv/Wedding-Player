async function afficherWorkflows(container, lireApi, preset = null) {
  container.innerHTML = '<section class="panel"><p role="status">Vérification du moteur local…</p></section>';
  const attente = container.querySelector('[role=status]');
  let agents;
  let local;
  try {
    const etat = await lireApi('/status');
    local = etat.workflows === true;
    agents = await lireApi('/agents');
  } catch {
    attente.textContent = 'Le serveur ORION ne répond pas.';
    return;
  }
  if (!attente.isConnected) return;

  container.innerHTML = `
    <section class="panel">
      <h2>Créer un workflow</h2>
      ${local ? '' : '<p class="mode-workflow">Simulation dans ce navigateur. La mission reste sur votre appareil. Ollama et la mémoire ChromaDB sont disponibles sur le serveur ORION local.</p>'}
      <form id="orion-workflow" class="workflow-form">
        <label>Mission<textarea name="task" required maxlength="8000" rows="4" placeholder="Décrivez le résultat attendu"></textarea></label>
        <div class="filters">
          <label>Agent<select name="agent" aria-label="Agent à ajouter"></select></label>
          <button type="button" data-add>Ajouter une étape</button>
        </div>
        <p>Sans étape, ORION sélectionne automatiquement un agent.</p>
        <ol data-steps></ol>
        <button type="submit">${local ? 'Exécuter' : 'Simuler le workflow'}</button>
      </form>
      <div data-result aria-live="polite"></div>
    </section>
    ${local ? `<section class="panel">
      <h2>Mémoire des workflows</h2>
      <form class="filters" id="orion-memory">
        <label>Rechercher dans les résultats<input name="q" type="search" maxlength="500" required></label>
        <button type="submit">Rechercher</button>
      </form>
      <div data-memory aria-live="polite"></div>
    </section>` : ''}`;
  const form = container.querySelector('#orion-workflow');
  const select = form.elements.agent;
  const steps = form.querySelector('[data-steps]');
  const add = form.querySelector('[data-add]');
  const result = container.querySelector('[data-result]');
  const ids = preset ? [...preset.agent_ids] : [];
  const catalogue = new Map(agents.map(agent => [agent.id, agent]));
  for (const agent of agents) select.add(new Option(agent.name + ' · ' + agent.team, agent.id));
  if (preset) form.elements.task.value = preset.task + '\n\nBrief : ';

  function actualiser() {
    steps.replaceChildren();
    ids.forEach((id, index) => {
      const li = document.createElement('li');
      li.append(catalogue.get(id).name + ' ');
      for (const [label, target] of [['Monter', index - 1], ['Descendre', index + 1], ['Retirer', null]]) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = label;
        btn.setAttribute('aria-label', label + ' ' + catalogue.get(id).name);
        btn.disabled = target !== null && (target < 0 || target >= ids.length);
        btn.onclick = () => {
          if (target === null) ids.splice(index, 1);
          else [ids[index], ids[target]] = [ids[target], ids[index]];
          actualiser();
        };
        li.append(btn);
      }
      steps.append(li);
    });
    for (const option of select.options) option.disabled = ids.includes(option.value);
    const disponible = [...select.options].find(option => !option.disabled);
    if (select.selectedOptions[0]?.disabled && disponible) select.value = disponible.value;
    add.disabled = ids.length >= 5 || !disponible;
  }
  add.onclick = () => {
    if (ids.length < 5 && catalogue.has(select.value) && !ids.includes(select.value)) {
      ids.push(select.value);
      actualiser();
    }
  };
  actualiser();

  function afficherTexte(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
  }

  async function json(response) {
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Requête refusée.');
    return data;
  }

  form.onsubmit = async event => {
    event.preventDefault();
    const body = {task: form.elements.task.value.trim(), agent_ids: ids.length ? [...ids] : null};
    if (!body.task) { result.textContent = 'Saisissez une mission.'; return; }
    const submit = form.querySelector('[type=submit]');
    submit.disabled = true;
    result.textContent = 'Exécution en cours…';
    try {
      const run = local
        ? await json(await fetch('/api/workflows', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
          }))
        : simulerWorkflow(body, agents);
      result.replaceChildren();
      afficherTexte(result, 'h3', !local ? 'Simulation terminée' : run.status === 'completed' ? 'Workflow terminé' : 'Workflow interrompu');
      if (local) afficherTexte(result, 'p', 'Identifiant · ' + run.id);
      if (run.error) afficherTexte(result, 'p', run.error);
      for (const step of run.steps) {
        afficherTexte(result, 'h4', (catalogue.get(step.agent)?.name || step.agent) + ' · ' + step.mode);
        afficherTexte(result, 'pre', step.result ?? 'Résultat non conservé.');
      }
    } catch (error) {
      result.textContent = 'Échec de l’exécution. ' + error.message;
    } finally {
      submit.disabled = false;
    }
  };

  if (!local) return;
  const memory = container.querySelector('#orion-memory');
  const matches = container.querySelector('[data-memory]');
  memory.onsubmit = async event => {
    event.preventDefault();
    const q = memory.elements.q.value.trim();
    if (!q) return;
    const button = memory.querySelector('[type=submit]');
    button.disabled = true;
    matches.textContent = 'Recherche en cours…';
    try {
      const hits = await json(await fetch('/api/memory/search?' + new URLSearchParams({q})));
      matches.replaceChildren();
      if (!hits.length) afficherTexte(matches, 'p', 'Aucun résultat indexé.');
      for (const hit of hits) {
        afficherTexte(matches, 'h4', (catalogue.get(hit.agent)?.name || hit.agent) + ' · Étape ' + hit.step);
        afficherTexte(matches, 'p', 'Workflow · ' + hit.workflow_id);
        afficherTexte(matches, 'pre', hit.text);
      }
    } catch (error) {
      matches.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
}

function simulerWorkflow(body, agents) {
  const normaliserTexte = value => value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const mission = ' ' + normaliserTexte(body.task) + ' ';
  let meilleur = agents.find(agent => agent.id === 'orion') || agents[0];
  let scoreMax = 0;
  if (!body.agent_ids) {
    for (const agent of agents) {
      const score = agent.capabilities.filter(cap => mission.includes(' ' + normaliserTexte(cap) + ' ')).length;
      if (score > scoreMax) {
        meilleur = agent;
        scoreMax = score;
      }
    }
  }
  const selection = body.agent_ids
    ? body.agent_ids.map(id => agents.find(agent => agent.id === id))
    : [meilleur];
  return {
    status: 'completed',
    steps: selection.map((agent, index) => ({
      agent: agent.id,
      mode: 'simulation',
      result: 'Étape ' + (index + 1) + ' · ' + agent.role + '\nCompétences : ' + agent.capabilities.join(', ')
    }))
  };
}


async function afficherWedding(container, lireApi, preferred) {
  container.innerHTML = `
    <div class="wedding-workspace">
      <div class="wedding-navigation" role="group" aria-label="Espace Wedding">
        <button type="button" data-wedding-tab="pilotage" aria-pressed="true">Pilotage</button>
        <button type="button" data-wedding-tab="dossiers" aria-pressed="false">Dossiers</button>
        <button type="button" data-wedding-tab="automations" aria-pressed="false">Modèles de workflows</button>
      </div>
      <div data-wedding-work data-wedding-view="pilotage"></div>
      <div data-wedding-models hidden>
        <section class="panel wedding-intro">
          <h2>Modèles du cycle mariage</h2>
          <div class="org-poles wedding-presets"></div>
          <p role="status">Chargement des modèles…</p>
        </section>
        <div class="wedding-workflow"></div>
      </div>
    </div>`;
  const work = container.querySelector('[data-wedding-work]');
  const models = container.querySelector('[data-wedding-models]');
  const tabs = [...container.querySelectorAll('[data-wedding-tab]')];
  function navigate(view) {
    work.dataset.weddingView = view;
    models.hidden = view !== 'automations';
    work.hidden = view === 'automations';
    for (const tab of tabs) tab.setAttribute('aria-pressed', String(tab.dataset.weddingTab === view));
  }
  for (const tab of tabs) tab.onclick = () => navigate(tab.dataset.weddingTab);
  const grille = container.querySelector('.wedding-presets');
  const attente = container.querySelector('[role=status]');
  const atelier = container.querySelector('.wedding-workflow');
  afficherChecklistWedding(work, lireApi, navigate, preferred);
  try {
    const presets = await lireApi('/wedding');
    if (!grille.isConnected) return;
    attente.remove();
    for (const preset of presets) {
      const bouton = document.createElement('button');
      bouton.type = 'button';
      bouton.className = 'wedding-preset';
      bouton.setAttribute('aria-pressed', 'false');
      const titre = document.createElement('strong');
      titre.textContent = preset.title;
      const texte = document.createElement('span');
      texte.textContent = preset.task;
      bouton.append(titre, texte);
      bouton.onclick = () => {
        for (const carte of grille.children) carte.setAttribute('aria-pressed', String(carte === bouton));
        afficherWorkflows(atelier, lireApi, preset);
        atelier.scrollIntoView({block:'start'});
      };
      grille.append(bouton);
    }
  } catch {
    attente.textContent = 'Les modèles Wedding sont indisponibles. Rechargez la page pour réessayer.';
  }
}
