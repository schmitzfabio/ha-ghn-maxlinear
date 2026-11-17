#!/usr/bin/env node
// Veröffentlichen statt ausrollen: „Ausrollen“ einer Home-Assistant-Integration ist ein GitHub-Release mit Tag v<version>.
// Die Version steht in custom_components/<domain>/manifest.json. Gleich in allen Integrations-Repos.
//
//   node release.mjs pruefen   Version lesen, Tag prüfen; schreibt RELEASE_TAG und LIVE_URL nach GITHUB_ENV.
//                              Zeigt v<version> schon auf einen anderen Commit: Fehler (Version in manifest.json erhöhen).
//   node release.mjs anlegen   Tag und Release für DEPLOY_SHA anlegen (Notizen automatisch); gibt es beides schon für
//                              genau diesen Stand, ist nichts zu tun.
//
// Umgebung: GITHUB_TOKEN (permissions: contents: write), GITHUB_REPOSITORY, DEPLOY_SHA, GITHUB_ENV (setzt GitHub).
// Ohne Abhängigkeiten, Node 18 oder neuer (fetch).

import fs from 'node:fs';
import path from 'node:path';

const env = process.env;
const api = `${(env.GITHUB_API_URL || 'https://api.github.com').replace(/\/+$/, '')}/repos/${env.GITHUB_REPOSITORY}`;

function abbruch(text) { console.error(`::error::${text}`); process.exit(1); }

async function gh(methode, pfad, body, { fehlendOk = false } = {}) {
  if (!env.GITHUB_TOKEN) abbruch('GITHUB_TOKEN fehlt (im Schritt per env setzen).');
  const r = await fetch(`${api}${pfad}`, {
    method: methode, signal: AbortSignal.timeout(30_000),
    headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${env.GITHUB_TOKEN}`, 'User-Agent': 'deploy', 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (fehlendOk && r.status === 404) return null;
  const text = await r.text();
  if (!r.ok) abbruch(`GitHub ${r.status} für ${methode} ${pfad}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

/** Version aus genau einer custom_components/<domain>/manifest.json. */
export function versionLesen(wurzel = '.') {
  const ordner = path.join(wurzel, 'custom_components');
  const dateien = fs.existsSync(ordner)
    ? fs.readdirSync(ordner).map(d => path.join(ordner, d, 'manifest.json')).filter(f => fs.existsSync(f))
    : [];
  if (dateien.length !== 1) abbruch(`Genau eine custom_components/*/manifest.json erwartet, gefunden: ${dateien.length}.`);
  const version = String(JSON.parse(fs.readFileSync(dateien[0], 'utf8')).version ?? '');
  if (!/^\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$/.test(version)) abbruch(`Version „${version}“ in ${dateien[0]} ist keine gültige Versionsnummer.`);
  return version;
}

/** Commit, auf den der Tag zeigt (auch bei annotierten Tags), sonst null. */
async function tagCommit(tag) {
  const ref = await gh('GET', `/git/ref/tags/${encodeURIComponent(tag)}`, null, { fehlendOk: true });
  if (!ref) return null;
  let obj = ref.object;
  while (obj && obj.type === 'tag') obj = (await gh('GET', `/git/tags/${obj.sha}`)).object;
  return obj?.sha ?? null;
}

function shaPruefen() {
  const sha = env.DEPLOY_SHA;
  if (!/^[0-9a-f]{40}$/.test(sha || '')) abbruch('DEPLOY_SHA muss der volle Commit sein (git rev-parse HEAD).');
  return sha;
}

async function pruefen() {
  const sha = shaPruefen();
  const tag = `v${versionLesen()}`;
  const ziel = await tagCommit(tag);
  if (ziel && ziel !== sha) {
    abbruch(`Tag ${tag} gibt es schon auf ${ziel.slice(0, 7)}, nicht auf ${sha.slice(0, 7)}: Version in manifest.json erhöhen.`);
  }
  const liveUrl = `${env.GITHUB_SERVER_URL || 'https://github.com'}/${env.GITHUB_REPOSITORY}/releases/tag/${tag}`;
  if (env.GITHUB_ENV) fs.appendFileSync(env.GITHUB_ENV, `RELEASE_TAG=${tag}\nLIVE_URL=${liveUrl}\n`);
  console.log(ziel ? `Tag ${tag} liegt schon auf ${sha.slice(0, 7)}.` : `Neuer Tag ${tag} für ${sha.slice(0, 7)}.`);
}

async function anlegen() {
  const sha = shaPruefen();
  const tag = env.RELEASE_TAG;
  if (!/^v\d/.test(tag || '')) abbruch('RELEASE_TAG fehlt (Schritt „pruefen“ gescheitert?).');
  const ziel = await tagCommit(tag);
  if (ziel && ziel !== sha) abbruch(`Tag ${tag} zeigt inzwischen auf ${ziel.slice(0, 7)}: Version in manifest.json erhöhen.`);
  const vorhanden = await gh('GET', `/releases/tags/${encodeURIComponent(tag)}`, null, { fehlendOk: true });
  if (vorhanden) { console.log(`Release ${tag} gibt es schon: ${vorhanden.html_url}`); return; }
  // Ohne Tag legt GitHub ihn mit dem Release auf target_commitish an; einen vorhandenen Tag (gleicher Stand) nimmt es unverändert.
  const rel = await gh('POST', '/releases', {
    tag_name: tag, target_commitish: sha, name: tag, generate_release_notes: true, make_latest: 'true',
  });
  console.log(`Release ${tag} für ${sha.slice(0, 7)} angelegt: ${rel.html_url}`);
}

const [befehl] = process.argv.slice(2);
if (import.meta.url === `file://${process.argv[1]}`) {
  if (befehl === 'pruefen') await pruefen();
  else if (befehl === 'anlegen') await anlegen();
  else abbruch('Aufruf: release.mjs pruefen | anlegen');
}
