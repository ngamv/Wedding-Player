const pages = {
  memoire: ['Mémoire', 'Capturez, classez et retrouvez vos informations métier.'],
  ceo: ['Brief du CEO', 'Les échéances et décisions à traiter dans vos activités.'],
  agenda: ['Agenda', 'Retrouvez vos rendez-vous, mariages et échéances dans un seul calendrier.'],
  validations: ['Validations', 'Examinez les propositions avant d’autoriser leur suite.'],
  recherche: ['Recherche', 'Retrouvez une fiche ou un document dans ORION.'],
  vue: ['Vue d’ensemble', 'Accédez aux indicateurs et aux priorités de vos activités.'],
  finances: ['Finances', 'Suivez les paiements encaissés et en attente.'],
  site: ['Site web', 'Raccordez vos sites et suivez leurs interventions.'],
  projets: ['Projets', 'Consultez les projets, leurs échéances et leur état.'],
  support: ['Support', 'Consultez les tickets et les priorités de traitement.'],
  organisation: ['Organigramme', 'Explorez les 15 pôles rattachés au CEO et les profils disponibles.'],
  agents: ['Agents IA', 'Consultez les profils spécialisés du catalogue ORION.'],
  wedding: ['Wedding Planner', 'Préparez chaque étape du mariage, du premier rendez-vous au bilan.'],
  workflows: ['Workflows', 'Composez une séquence d’agents et consultez la mémoire locale.'],
  backend: ['Backend', 'Vérifiez la connexion au service et consultez ses réponses JSON.'],
};
const content = document.querySelector('#content');
let currentRows = [];

function escape(value) {
  const span = document.createElement('span');
  span.textContent = value;
  return span.innerHTML;
}
function table(rows, headings) {
  return '<div class="table-wrap"><table><thead><tr>'+headings.map(x=>'<th scope="col">'+escape(x)+'</th>').join('')+
    '</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+escape(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}
function panel(title, inner) {
  return '<section class="panel"><div class="panel-head"><h2>'+title+'</h2></div>'+inner+'</section>';
}
const api = '/api/dashboard';
const outils = '<button type="button" id="refresh">Actualiser</button>';
const normaliser = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

async function lireApi(route) {
  const response = await fetch(api + route, {cache:'no-store', signal:AbortSignal.timeout(8000)});
  if(!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

async function afficherBackend() {
  content.innerHTML = panel('Exploitation locale', outils +
    '<p role="status" id="backend-status">Vérification des services…</p>' +
    '<div data-services></div><h3>Bilan de mise en service</h3><div data-capabilities></div><h3>Sauvegarde SQLite</h3><div data-backup></div>' +
    '<h3>Exécutions du brief Wedding</h3><div data-brief-runs></div>' +
    '<div class="api-links"><a href="' + api + '/status" target="_blank" rel="noopener">État JSON</a>' +
    '<a href="' + api + '/agents" target="_blank" rel="noopener">Catalogue JSON</a></div>');
  content.querySelector('#refresh').addEventListener('click', afficherBackend);
  const status = content.querySelector('#backend-status');
  const services = content.querySelector('[data-services]');
  const capabilities = content.querySelector('[data-capabilities]');
  const history = content.querySelector('[data-brief-runs]');
  const backup = content.querySelector('[data-backup]');
  const date = new Intl.DateTimeFormat('fr-FR', {
    dateStyle:'medium', timeStyle:'short', timeZone:'Europe/Paris',
  });
  try {
    const data = await lireApi('/local-operations');
    const labels = {online:'En ligne', warning:'À vérifier', error:'Indisponible'};
    const rows = Object.entries(data.services).map(([name, value]) => [name, labels[value.state], value.detail]);
    services.innerHTML = table(rows, ['Service', 'État', 'Diagnostic']);
    const readiness = {ready:'Disponible', action:'À configurer', check:'À tester', disabled:'Désactivé'};
    capabilities.innerHTML = table(Object.entries(data.capabilities).map(([name, value]) =>
      [name, readiness[value.state], value.detail]), ['Fonction', 'État', 'Diagnostic']);
    const snapshot = data.backup;
    const states = {verified:'Archive vérifiée', failed:'Dernière tentative en échec', missing:'Archive introuvable'};
    if (snapshot) {
      const info = document.createElement('p');
      info.textContent = states[snapshot.state] || 'État de la sauvegarde indisponible';
      backup.append(info);
      if (snapshot.verified?.at && snapshot.state !== 'missing') {
        const last = document.createElement('p');
        last.textContent = 'Dernière archive vérifiée · ' + date.format(new Date(snapshot.verified.at)) +
          ' · ' + snapshot.verified.archive +
          (snapshot.verified.manifest_verified ? ' · Empreintes SHA-256 vérifiées' : '');
        backup.append(last);
      }
    } else {
      backup.textContent = 'Aucune sauvegarde quotidienne enregistrée.';
    }
    const origins = {dashboard:'Tableau de bord', n8n:'n8n', scheduler:'Rappel local'};
    const runs = data.brief_runs.map(run => [
      date.format(new Date(run.finished_at.replace(' ', 'T') + 'Z')),
      origins[run.origin],
      run.state === 'completed' ? 'Terminé' : 'Échec',
    ]);
    history.innerHTML = runs.length ? table(runs, ['Heure de Paris', 'Origine', 'Résultat'])
      : '<p>Aucune exécution enregistrée.</p>';
    status.textContent = 'Mode ORION · ' + data.mode;
    if (data.brief_runs[0]?.state === 'failed') {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Relancer la génération du brief';
      retry.onclick = async () => {
        retry.disabled = true;
        status.textContent = 'Génération du brief…';
        try {
          const response = await fetch('/api/wedding/brief', {method:'POST'});
          if (!response.ok) throw new Error();
          afficherBackend();
        } catch {
          status.textContent = 'La génération du brief a échoué. Consultez les journaux locaux.';
          retry.disabled = false;
        }
      };
      history.append(retry);
    }
  } catch {
    status.textContent = 'Diagnostic indisponible. Vérifiez que le serveur ORION local est démarré.';
  }
}

async function afficherOrganisation() {
  content.innerHTML=panel('Organisation ORION', outils+'<p role="status">Chargement de l’organigramme…</p>');
  content.querySelector('#refresh').addEventListener('click', afficherOrganisation);
  const attente=content.querySelector('[role="status"]');
  try {
    const [organisation, agents]=await Promise.all([lireApi('/organisation'),lireApi('/agents')]);
    if(!attente.isConnected) return;
    const rattachement=agent=>organisation.affectations[agent.id]||agent.team;
    const direction=agents.filter(agent=>rattachement(agent)==='cio');
    const profils=liste=>liste.map(agent=>'<li><strong>'+escape(agent.name)+'</strong><span>'+escape(agent.role)+'</span></li>').join('');
    const cartes=organisation.poles.map(pole=>{
      const membres=agents.filter(agent=>rattachement(agent)===pole.id);
      return '<details class="pole"><summary><strong>'+escape(pole.nom)+'</strong><span>'+
        (membres.length?membres.length+' profil'+(membres.length>1?'s':''):'À pourvoir')+
        '</span></summary>'+(membres.length?'<ul class="pole-profils">'+profils(membres)+'</ul>':
        '<p>Aucun profil rattaché à ce pôle.</p>')+'</details>';
    }).join('');
    content.innerHTML=panel('Direction et pôles',
      '<div class="org-direction"><div><strong>'+escape(organisation.direction)+'</strong>'+
      '<span>Direction générale</span></div>'+(direction.length?'<ul class="pole-profils">'+profils(direction)+'</ul>':'')+
      '</div><p class="org-legende">'+organisation.poles.length+' pôles rattachés au CEO</p>'+
      '<div class="org-poles">'+cartes+'</div>');
  } catch {
    attente.textContent='Organigramme indisponible. Utilisez Actualiser pour réessayer.';
  }
}

async function afficherAgents() {
  currentRows=[];
  content.innerHTML=panel('Catalogue ORION', outils + '<p role="status">Chargement des profils…</p>');
  content.querySelector('#refresh').addEventListener('click', afficherAgents);
  const attente = content.querySelector('[role="status"]');
  let agents;
  try {
    agents = await lireApi('/agents');
    if(!Array.isArray(agents)) throw new Error('Catalogue invalide');
  } catch {
    attente.textContent='Catalogue indisponible. Utilisez Actualiser pour réessayer.';
    return;
  }
  if(!attente.isConnected) return;
  content.innerHTML=panel('Catalogue ORION',
    '<div class="filters"><label>Rechercher<input type="search" id="agent-search" placeholder="Nom, rôle ou capacité"></label>' +
    '<label>Équipe<select id="agent-team"><option value="">Toutes les équipes</option></select></label>' +
    outils + '</div><p role="status" id="agent-count"></p><div id="agent-results"></div>');
  const search=content.querySelector('#agent-search');
  const team=content.querySelector('#agent-team');
  for(const name of [...new Set(agents.map(a=>a.team))].sort()) team.add(new Option(name,name));
  const headings=['Agent','Équipe','Rôle','Capacités'];
  function filtrer() {
    const q=normaliser(search.value.trim());
    const rows=agents
      .filter(a=>(!team.value||a.team===team.value)&&normaliser([a.name,a.team,a.role,...a.capabilities].join(' ')).includes(q))
      .map(a=>[a.name,a.team,a.role,a.capabilities.join(', ')]);
    currentRows=[headings,...rows];
    content.querySelector('#agent-count').textContent=rows.length+' / '+agents.length+' profils';
    content.querySelector('#agent-results').innerHTML=rows.length?table(rows,headings):'<p>Aucun profil ne correspond aux filtres.</p>';
  }
  search.addEventListener('input',filtrer);
  team.addEventListener('change',filtrer);
  content.querySelector('#refresh').addEventListener('click',afficherAgents);
  filtrer();
}

let previousPage;

async function render(){
  const [requested, query]=location.hash.slice(1).split('?', 2);
  const params = new URLSearchParams(query);
  const page=Object.hasOwn(pages,requested)?requested:'vue';
  const [title,sub]=pages[page];
  if(previousPage!==page && !matchMedia('(prefers-reduced-motion: reduce)').matches){
    document.querySelector('.heading').animate([{opacity:.65,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'ease-out'});
  }
  previousPage=page;
  document.body.dataset.page=page;
  document.querySelector('.hero-links').hidden=page!=='vue';
  document.querySelector('#title').textContent=title;
  document.querySelector('#crumb').textContent=title;
  document.querySelector('#subtitle').textContent=sub;
  for(const a of document.querySelectorAll('nav a')){
    if(a.hash==='#'+page) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
  }
  currentRows=[];
  document.querySelector('#export').hidden=true;
  if(page==='recherche'){
    afficherRecherche(content, params.get('q'));
    return;
  }
  if(page==='validations'){
    afficherValidations(content);
    return;
  }
  if(page==='agenda'){
    afficherAgenda(content, params.get('date'), params.get('rdv'));
    return;
  }
  if(page==='projets'){
    afficherProjets(content, params.get('projet'), params.get('tache'), params.has('planning'));
    return;
  }
  if(page==='finances'){
    afficherFinances(content);
    return;
  }
  if(page==='support'){
    afficherSupport(content, params.get('ticket'));
    return;
  }
  if(page==='ceo'){
    afficherBriefCEO(content, params.has('imports'));
    return;
  }
  if(page==='memoire'){
    afficherInbox(content, params.get('entree'), params.get('projet'));
    return;
  }
  if(page==='site'){
    afficherSites(content, params.get('dossier'), params.get('intervention'));
    return;
  }
  if(page==='wedding'){
    afficherWedding(content, lireApi, params.get('dossier'), params.get('relance'));
    return;
  }
  if(page==='workflows'){
    afficherWorkflows(content, lireApi);
    return;
  }
  if(page==='organisation'){
    afficherOrganisation();
    return;
  }
  if(page==='agents'){
    afficherAgents();
    return;
  }
  if(page==='backend'){
    afficherBackend();
    return;
  }
  afficherVueEnsemble(content, rows => {
    currentRows=rows;
    document.querySelector('#export').hidden=!rows.length;
  });
}
window.addEventListener('hashchange',render);
const menu=document.querySelector('#menu');
function ouvrirMenu(ouvert) {
  menu.setAttribute('aria-expanded',String(ouvert));
  document.querySelector('#navigation').classList.toggle('is-open',ouvert);
}
menu.onclick=()=>ouvrirMenu(menu.getAttribute('aria-expanded')!=='true');
document.querySelector('#navigation').addEventListener('click',event=>{
  if(event.target.closest('a')&&menu.getAttribute('aria-expanded')==='true') {
    ouvrirMenu(false);
    content.focus({preventScroll:true});
  }
});
document.querySelector('aside').addEventListener('keydown',event=>{
  if(event.key==='Escape'&&menu.getAttribute('aria-expanded')==='true') {
    ouvrirMenu(false);
    menu.focus();
  }
});
document.querySelector('#skip-content').onclick=event=>{
  event.preventDefault();
  content.focus();
};

document.querySelector('#export').addEventListener('click',()=>{
  if(!currentRows.length) return;
  const csv=currentRows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(';')).join('\r\n');
  const url=URL.createObjectURL(new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='orion-'+(location.hash.slice(1)||'vue')+'.csv';a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
async function afficherEtatApi() {
  const indicateur=document.querySelector('#api-indicator');
  try {
    const etat=await lireApi('/status');
    if(etat.status!=='online') throw new Error('État indisponible');
    indicateur.textContent=etat.recovery?'Copie de restauration':(etat.workflows?'Moteur local':'Service en ligne');
    if(etat.recovery) indicateur.dataset.recovery='true';
    indicateur.dataset.state='online';
  } catch {
    indicateur.textContent='API indisponible';
    indicateur.dataset.state='offline';
  }
  indicateur.hidden=false;
}
afficherEtatApi();
initialiserSessionOrion();
render();
