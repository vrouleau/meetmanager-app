---
title: "Meet Manager — Guide rapide du flux de travail"
date: "2026"
mainfont: "Lato"
monofont: "Noto Mono"
fontsize: 11pt
geometry: "margin=2.5cm"
colorlinks: true
urlcolor: "NavyBlue"
linkcolor: "NavyBlue"
header-includes:
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhf{}
  - \fancyhead[L]{\textit{Meet Manager}}
  - \fancyhead[R]{\textit{Guide rapide}}
  - \fancyfoot[C]{\thepage}
  - \usepackage{titlesec}
  - \usepackage{xcolor}
  - \definecolor{primary}{RGB}{30,64,175}
  - \titleformat{\section}{\Large\bfseries\color{primary}}{}{0em}{}[\vspace{-0.5ex}\rule{\textwidth}{0.4pt}]
  - \titleformat{\subsection}{\normalsize\bfseries}{}{0em}{}
---

# Meet Manager — Guide rapide du flux de travail

## Prérequis

- SPLASH Meet Manager 11
- Application Meet Manager en marche (Docker)
- Accès admin à l'application (NIP admin)

---

## Étape 1 — Admin : Configurer les clubs et les athlètes

1. Se connecter à l'application Meet Manager en tant qu'**Admin**
2. Dans la page **Admin**, téléverser un fichier Lenex `.lxf` d'inscriptions (compétition précédente ou liste principale) pour importer les clubs, athlètes et meilleurs temps
3. Réviser la liste des clubs ; ajouter ou supprimer au besoin
4. Désigner le **club organisateur** dans *Désigner l'organisateur*

---

## Étape 2 — Organisateur : Obtenir le gabarit de compétition

1. Se connecter en tant qu'**Organisateur** (club désigné par l'Admin)
2. Dans la page **Organisateur**, cliquer **Télécharger le gabarit de compétition (.lxf)**
3. Ouvrir le fichier `.lxf` téléchargé dans SPLASH — ceci restaure la structure de la compétition précédente comme point de départ
4. Dans SPLASH, mettre à jour la compétition : dates, sessions, épreuves, tarifs et autres détails

---

## Étape 3 — Exporter l'invitation depuis SPLASH

![Exporter l'invitation depuis SPLASH](assets/1_export_invitation.png)

1. Dans SPLASH, aller dans **Transferts → Exporter l'invitation…**
2. Sauvegarder le fichier `.lxf` résultant (c'est la structure mise à jour de la compétition)

---

## Étape 4 — Organisateur : Téléverser la structure de la compétition

1. Dans la page **Organisateur**, cliquer **Téléverser structure (.lxf)** et sélectionner le `.lxf` exporté à l'étape 3
2. L'application charge toutes les épreuves, la taille du bassin, le drapeau Masters et les tarifs
3. La boîte **Résumé des frais** affichera les tarifs de la compétition et par épreuve

---

## Étape 5 — Organisateur : Fixer la date limite d'inscription

1. Dans la page **Organisateur**, définir la **Date limite d'inscription**
2. Les responsables de club peuvent inscrire jusqu'à cette date ; la liste des invitations devient grisée après la clôture

---

## Étape 6 — Organisateur : Envoyer les invitations aux responsables

1. Dans la page **Organisateur**, aller dans **Invitations aux équipes**
2. Sélectionner les clubs à inviter (cases à cocher ou tout sélectionner)
3. Cliquer **Envoyer l'invitation** — chaque responsable reçoit un courriel avec un lien sécurisé à usage unique pour récupérer le NIP de son club

---

## Étape 7 — Les responsables inscrivent les athlètes

![Modifier les inscriptions](assets/3_editentries.png)

1. Le responsable clique sur le lien NIP reçu par courriel pour révéler le NIP de son club
2. Se connecter avec le NIP
3. Sélectionner un athlète → la page d'inscription s'ouvre
4. Cocher les épreuves ; sélectionner la catégorie (15-18 / Open / Masters)
5. Les meilleurs temps (50m et 25m) sont affichés en lecture seule
6. Le temps d'inscription est pré-rempli à partir du meilleur temps correspondant au bassin ; ajuster si nécessaire

---

## Étape 8 — Organisateur : Exporter les inscriptions

1. Après la date limite, dans la page **Organisateur** cliquer **Télécharger le bundle (.zip)**
2. Le zip contient le fichier `.lxf` des inscriptions et les scripts d'aide à la simulation de résultats SPLASH

---

## Étape 9 — Importer les inscriptions dans SPLASH

![Importer les inscriptions dans SPLASH](assets/2_importentries.png)

1. Dans SPLASH, aller dans **Transferts → Importer les inscriptions…**
2. Sélectionner le `.lxf` contenu dans le zip téléchargé
3. Tous les athlètes, clubs et temps d'inscription sont importés et prêts pour le jour de la compétition

---

## Étape 10 — Après la compétition : Exporter les résultats depuis SPLASH

![Exporter les résultats depuis SPLASH](assets/4_exportresults.png)

1. Après la compétition, dans SPLASH aller dans **Transferts → Exporter les résultats…**
2. Sauvegarder le fichier `.lxf` des résultats

---

## Étape 11 — Admin : Téléverser les résultats pour mettre à jour les meilleurs temps

1. Dans la page **Admin**, téléverser le fichier `.lxf` des résultats sous **Téléverser Lenex (.lxf)**
2. Les meilleurs temps sont mis à jour (le plus rapide entre le temps d'inscription et le résultat, par taille de bassin)
3. Ces temps pré-rempliront les temps d'inscription pour la prochaine compétition

---

## Étape 12 — Admin : Exporter le fichier d'inscriptions mis à jour

1. Dans la page **Gestion des données**, cliquer **Télécharger les inscriptions (.lxf)**
2. Sauvegarder ce fichier — l'utiliser comme point de départ pour la prochaine compétition (Étape 1)

---

## Résumé

| Étape | Action | Qui | Outil |
|-------|--------|-----|-------|
| 1 | Importer clubs et athlètes ; désigner l'organisateur | Admin | Meet Manager App |
| 2 | Télécharger le gabarit de compétition | Organisateur | Meet Manager App |
| 3 | Mettre à jour la compétition dans SPLASH ; exporter l'invitation | Organisateur | SPLASH |
| 4 | Téléverser la structure de la compétition | Organisateur | Meet Manager App |
| 5 | Fixer la date limite | Organisateur | Meet Manager App |
| 6 | Envoyer les invitations | Organisateur | Meet Manager App |
| 7 | Inscrire les athlètes | Responsables | Meet Manager App |
| 8 | Exporter le bundle d'inscriptions (.zip) | Organisateur | Meet Manager App |
| 9 | Importer les inscriptions | Organisateur | SPLASH |
| 10 | Exporter les résultats | — | SPLASH |
| 11 | Téléverser résultats / mettre à jour les meilleurs temps | Admin | Meet Manager App |
| 12 | Exporter le fichier d'inscriptions mis à jour | Admin | Meet Manager App |
