#!/usr/bin/env node
// Einheitlicher Deploy aller Repos (Vorlage aus deploy/ausrollen/ der Cockpit-Software, unverändert nach .github/deploy/deployment.mjs kopieren).
// Meldet den Deploy als GitHub-Deployment (Umgebung „production“) und prüft danach an der Versionsadresse, ob genau dieser Stand live ist.
// Das Cockpit liest den Live-Stand aller Repos einheitlich über die Deployments-API und prüft ihn an derselben Adresse gegen.
//
//   node deployment.mjs start                    Deployment für DEPLOY_SHA anlegen, Status in_progress; schreibt id=<n> nach GITHUB_OUTPUT
//   node deployment.mjs pruefen                  warten, bis VERSION_URL (Feld VERSION_FELD) DEPLOY_SHA meldet (höchstens PRUEF_SEK, Standard 300)
//   node deployment.mjs ende <id> <success|failure>
//
// Umgebung: GITHUB_TOKEN (permissions: deployments: write), GITHUB_REPOSITORY, GITHUB_SERVER_URL, GITHUB_RUN_ID (setzt GitHub),
// DEPLOY_SHA, UMGEBUNG (Standard production), VERSION_URL, VERSION_FELD (Pfad im JSON, z. B. „backend.version“; leer: Feld „commit“
// oder die ganze Antwort als Text), LIVE_URL (Adresse des Live-Systems für die Anzeige, optional).
// Ohne Abhängigkeiten, Node 18 oder neuer (fetch).

import fs from 'node:fs';

const env = process.env;
const api = `${(env.GITHUB_API_URL || 'https://api.github.com').replace(/\/+$/, '')}/repos/${env.GITHUB_REPOSITORY}`;
const umgebung = env.UMGEBUNG || 'production';

function abbruch(text) { console.error(`::error::${text}`); process.exit(1); }

async function gh(methode, pfad, body) {
  if (!env.GITHUB_TOKEN) abbruch('GITHUB_TOKEN fehlt (im Schritt per env setzen).');
  const r = await fetch(`${api}${pfad}`, {
    method: methode, signal: AbortSignal.timeout(30_000),
    headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${env.GITHUB_TOKEN}`, 'User-Agent': 'deploy', 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  if (!r.ok) abbruch(`GitHub ${r.status} für ${methode} ${pfad}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

/** Commit aus der Antwort der Versionsadresse: Feldpfad, sonst „commit“, sonst Text; der erste Hex-Block mit 7 bis 40 Zeichen. */
export function commitAus(text, feld) {
  let wert = text;
  try {
    const j = JSON.parse(text);
    const pfad = feld ? feld.split('.') : (j && typeof j === 'object' && 'commit' in j ? ['commit'] : []);
    wert = pfad.reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), j);
    if (!pfad.length) wert = typeof j === 'string' ? j : text;
  } catch { /* kein JSON: Text */ }
  const m = String(wert ?? '').toLowerCase().match(/(?:^|[^0-9a-f])([0-9a-f]{7,40})(?![0-9a-f])/);
  return m ? m[1] : null;
}

/** Gleicher Stand, wenn einer der beiden mit dem anderen beginnt (Kurz- gegen Langform), mindestens 7 Zeichen. */
export const gleicherStand = (a, b) => !!a && !!b && Math.min(a.length, b.length) >= 7 && (a.toLowerCase().startsWith(b.toLowerCase()) || b.toLowerCase().startsWith(a.toLowerCase()));

const logUrl = () => `${env.GITHUB_SERVER_URL || 'https://github.com'}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`;

async function start() {
  const sha = env.DEPLOY_SHA;
  if (!/^[0-9a-f]{40}$/.test(sha || '')) abbruch('DEPLOY_SHA muss der volle Commit sein (git rev-parse HEAD).');
  const d = await gh('POST', '/deployments', {
    ref: sha, environment: umgebung, auto_merge: false, required_contexts: [], production_environment: umgebung === 'production',
    description: `Deploy ${sha.slice(0, 7)} (Lauf ${env.GITHUB_RUN_ID})`, payload: { lauf: Number(env.GITHUB_RUN_ID) || null },
  });
  await gh('POST', `/deployments/${d.id}/statuses`, { state: 'in_progress', log_url: logUrl(), ...(env.LIVE_URL ? { environment_url: env.LIVE_URL } : {}) });
  if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, `id=${d.id}\n`);
  console.log(`Deployment ${d.id} für ${sha.slice(0, 7)} (${umgebung}) gemeldet.`);
}

async function pruefen() {
  const sha = env.DEPLOY_SHA;
  if (!env.VERSION_URL) { console.log('Keine VERSION_URL: Live-Stand wird nicht geprüft.'); return; }
  const bis = Date.now() + (Number(env.PRUEF_SEK) || 300) * 1000;
  let zuletzt = 'keine Antwort';
  while (Date.now() < bis) {
    try {
      const r = await fetch(`${env.VERSION_URL}${env.VERSION_URL.includes('?') ? '&' : '?'}t=${Date.now()}`, { signal: AbortSignal.timeout(15_000), headers: { 'Cache-Control': 'no-cache' } });
      const live = r.ok ? commitAus(await r.text(), env.VERSION_FELD) : null;
      zuletzt = r.ok ? (live ?? 'kein Commit in der Antwort') : `HTTP ${r.status}`;
      if (gleicherStand(live, sha)) { console.log(`Live: ${live} (${env.VERSION_URL})`); return; }
    } catch (e) { zuletzt = e instanceof Error ? e.message : String(e); }
    await new Promise(ok => setTimeout(ok, 10_000));
  }
  abbruch(`Versionsadresse meldet nicht ${sha.slice(0, 7)}, zuletzt: ${zuletzt}`);
}

async function ende(id, zustand) {
  if (!/^\d+$/.test(id || '')) abbruch('Deployment-id fehlt (Schritt „start“ gescheitert?).');
  if (!['success', 'failure'].includes(zustand)) abbruch('Zustand: success oder failure.');
  await gh('POST', `/deployments/${id}/statuses`, {
    state: zustand, log_url: logUrl(), auto_inactive: zustand === 'success', ...(env.LIVE_URL ? { environment_url: env.LIVE_URL } : {}),
    description: zustand === 'success' ? 'live und geprüft' : 'gescheitert',
  });
  console.log(`Deployment ${id}: ${zustand}`);
}

const [befehl, ...rest] = process.argv.slice(2);
if (import.meta.url === `file://${process.argv[1]}`) {
  if (befehl === 'start') await start();
  else if (befehl === 'pruefen') await pruefen();
  else if (befehl === 'ende') await ende(rest[0], rest[1]);
  else abbruch('Aufruf: deployment.mjs start | pruefen | ende <id> <success|failure>');
}
