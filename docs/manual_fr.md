# Vue d'ensemble

**Meet Manager** est une application web de gestion des inscriptions aux compétitions de sauvetage sportif. Les clubs se connectent avec un NIP, inscrivent leurs athlètes aux épreuves, et l'organisateur supervise la configuration de la compétition, les invitations et l'export. Un administrateur gère la plateforme globale.

L'application fonctionne en complément de **SPLASH Meet Manager 11** : la structure de la compétition est exportée depuis SPLASH et téléversée dans Meet Manager App, puis les inscriptions finales sont réexportées vers SPLASH avant le jour de la compétition.

## Rôles

| Rôle | Description |
|------|-------------|
| **Admin** | Accès complet. Gère les clubs, les athlètes, la configuration de l'application, la désignation de l'organisateur, la gestion des données et le téléversement des résultats. |
| **Organisateur** | Un club désigné par l'Admin. Téléverse la structure de la compétition, fixe la date limite, envoie les invitations, gère la facturation Stripe et exporte les inscriptions. Accède aussi à Athlètes. |
| **Responsable** | Connexion d'un club. Consulte et gère ses propres athlètes et inscriptions. |

Le NIP admin est défini dans le fichier `.env` (défaut : `314159`) et peut être modifié dans la page Admin. Chaque club possède un NIP à 6 chiffres généré par le système. Un organisateur se connecte avec le NIP de son club et obtient l'accès Organisateur parce que son club est marqué comme organisateur.

## Navigation

Après la connexion, la barre de navigation affiche des liens selon votre rôle :

- **Athlètes** — visible pour tous les rôles
- **Organisateur** — visible pour Admin et Organisateur
- **Admin** — visible uniquement pour Admin
- **Gestion des données** — visible uniquement pour Admin

Le nom de la compétition en cours est affiché dans la barre de navigation lorsqu'une compétition est chargée. La langue peut être basculée (FR / EN) depuis n'importe quelle page.

---

# Guide Admin

## Connexion en tant qu'Admin

Entrer le NIP admin sur la page de connexion. Le NIP par défaut est `314159`. Après la connexion, le rôle est `admin`.

## Vue d'ensemble du statut

Le haut de la page Admin affiche un décompte en temps réel : clubs, athlètes, épreuves, inscriptions et meilleurs temps dans la base de données.

## Téléverser clubs et athlètes (Lenex)

La section **Téléverser Lenex (.lxf)** accepte un fichier `.lxf` au format Lenex (export d'inscriptions ou de résultats depuis SPLASH). Au téléversement :

- Un aperçu indique le nombre de clubs et d'athlètes dans le fichier et combien sont nouveaux
- Confirmer pour continuer — les clubs et athlètes existants sont associés par code de club et numéro de licence NRAN, sans modification
- Les nouveaux meilleurs temps sont importés et fusionnés (le temps le plus rapide par style et par taille de bassin est conservé)
- Chaque meilleur temps est horodaté avec la date de la compétition source. Les temps de plus de 18 mois sont automatiquement supprimés à l'ouverture de la page d'inscription d'un athlète.

Utiliser cette fonction pour initialiser l'application avant la première compétition de la saison, ou après chaque compétition pour importer les résultats.

## Gestion des clubs

Le tableau **Gestion des clubs** liste tous les clubs avec leur NIP, courriel et nombre d'athlètes.

- **Modifier le courriel** : cliquer sur le champ courriel et modifier en place ; les modifications sont sauvegardées en quittant le champ
- **Supprimer un club** : supprime le club ainsi que tous ses athlètes, inscriptions et meilleurs temps (confirmation requise)
- **Ajouter un club** : entrer un nom et un courriel optionnel, puis cliquer Ajouter — un NIP à 6 chiffres est généré automatiquement

## Régénérer tous les NIPs de club

Le bouton **Régénérer tous les NIPs** génère de nouveaux NIPs à 6 chiffres pour chaque club. Utiliser cette fonction pour révoquer toutes les connexions existantes (ex. : entre les saisons). Les responsables devront recevoir leurs nouveaux NIPs via le processus d'invitation.

## Changer le NIP Admin

Entrer un nouveau NIP (minimum 4 caractères) dans le formulaire **Changer le PIN admin** et soumettre. Le nouveau NIP prend effet immédiatement. La session est mise à jour automatiquement.

## Désigner l'organisateur

La section **Désigner l'organisateur** permet d'assigner un club comme organisateur de la compétition en cours. Le responsable du club désigné verra la page **Organisateur** en plus d'**Athlètes**. Un seul organisateur est actif à la fois. La désignation est effacée lors de la réinitialisation de la compétition.

## Réinitialiser la compétition

Le bouton **Réinitialiser la compétition** supprime :

- Toutes les inscriptions
- Toutes les épreuves (structure de la compétition)
- La désignation de l'organisateur
- Les métadonnées de la compétition (nom, dates, tarifs, date limite)

Les clubs, athlètes, meilleurs temps et NIPs **ne sont pas** supprimés. Utiliser cette fonction pour réinitialiser l'application entre les compétitions tout en conservant la base de données des athlètes.

## Téléverser les résultats (après la compétition)

Après la compétition, exporter les résultats depuis SPLASH et téléverser le fichier `.lxf` de résultats dans la section **Téléverser Lenex (.lxf)**. L'application importe les résultats et met à jour les meilleurs temps : pour chaque athlète et chaque style d'épreuve, le plus rapide entre le temps existant et le nouveau résultat est conservé, séparément pour LCM (50m) et SCM (25m).

---

# Guide Organisateur

## Accéder à la page Organisateur

Se connecter avec le NIP de son club. Parce que le club a été désigné organisateur par l'Admin, les pages **Athlètes** et **Organisateur** sont visibles dans la navigation.

## Bannière d'information de la compétition

Le haut de la page Organisateur affiche la compétition chargée : nom, taille du bassin (50m / 25m), drapeau Masters, nombre d'épreuves, nom du fichier et date de téléversement. Si aucune compétition n'est chargée, un avertissement est affiché.

## Résumé des frais

La boîte **Résumé des frais** (déroulante, police monospace) affiche :

- **Frais au niveau de la compétition** : par club, par athlète, par équipe de relais, par équipe, frais d'inscription tardive, frais LSC
- **Frais par inscription, par épreuve** : numéro d'épreuve, nom du style et montant

Ces frais sont lus depuis la structure `.lxf` de la compétition et servent à calculer le total de chaque club pour la facturation.

## Télécharger le gabarit de compétition

Cliquer **Télécharger le gabarit de compétition (.lxf)** pour télécharger le fichier de base de la compétition. Ouvrir ce fichier dans SPLASH pour restaurer la structure de la compétition précédente comme point de départ. Personnaliser les épreuves, sessions, dates et tarifs dans SPLASH, puis exporter l'invitation `.lxf` et la téléverser.

## Téléverser la structure de la compétition

Cliquer **Téléverser structure (.lxf)** et sélectionner le fichier `.lxf` d'invitation exporté depuis SPLASH. Ceci charge la structure des épreuves dans l'application. Si une compétition est déjà chargée, un avertissement explique que toutes les inscriptions en cours, la date limite et les NIPs de club seront réinitialisés — confirmer pour continuer.

## Fixer la date limite d'inscription

Cliquer sur le champ de date dans la ligne **Date limite d'inscription** et sélectionner le dernier jour pour les inscriptions. Sauvegarder en cliquant en dehors du champ. Après le passage de la date limite :

- Les inscriptions ne sont plus acceptées des responsables
- Le tableau d'invitations devient grisé (les invitations peuvent techniquement encore être envoyées, mais les inscriptions sont fermées)
- Les boutons de facturation deviennent actifs (les factures Stripe ne peuvent être envoyées qu'après la clôture)

## Envoyer les invitations

Le tableau **Invitations aux équipes** liste tous les clubs avec leur courriel et leur statut de facturation.

- **Envoyer aux sélectionnés** : cocher les clubs à inviter et cliquer **Envoyer l'invitation (n)**
- Chaque responsable reçoit un courriel avec un lien sécurisé à usage unique. Le lien révèle le NIP du club lorsqu'on clique dessus. Le lien expire après 48 heures et ne peut être utilisé qu'une seule fois.

> Les clubs sans adresse courriel ne peuvent pas recevoir d'invitations. Définir le courriel dans Admin → Gestion des clubs.

## Exporter les inscriptions

Cliquer **Télécharger le bundle (.zip)** pour exporter les inscriptions. Le zip contient :

- Un fichier Lenex `.lxf` avec toutes les inscriptions, athlètes, clubs et temps d'inscription
- `simulate_results.bat` — un lanceur Windows pour le script de simulation
- `simulate_results.vbs` — un script VBScript pour simuler les résultats dans SPLASH le jour de la compétition

Importer le `.lxf` dans SPLASH via **Transferts → Importer les inscriptions…** pour charger tous les athlètes et temps d'inscription pour le jour de la compétition.

## Facturation Stripe

### Connecter Stripe

Cliquer **Connecter Stripe** pour lancer le processus d'autorisation Stripe Connect OAuth. Vous serez redirigé vers Stripe pour autoriser la connexion. Une fois connecté, le bouton affiche un indicateur vert « Connecté » avec une option Déconnecter.

### Envoyer les factures

Après la date limite, chaque ligne du tableau **Invitations aux équipes** affiche un bouton **Envoyer la facture (montant)** si :

- Le club a au moins une inscription (total de facturation > 0)
- Votre compte Stripe est connecté

Cliquer pour créer et envoyer une facture Stripe au club via votre compte Stripe connecté. La facture est calculée à partir de la structure tarifaire dans le fichier `.lxf`.

### Télécharger les factures PDF (sans Stripe)

Si Stripe n'est pas connecté, un bouton **Télécharger la facture** apparaît à la place. Ceci génère une facture PDF (via reportlab sur le serveur) téléchargeable pour envoi manuel.

### Calcul des factures

Chaque facture comprend :

| Ligne | Règle |
|-------|-------|
| Par club | 1 × frais de club |
| Par athlète | Nombre d'athlètes avec au moins 1 inscription × frais par athlète |
| Par relais | Nombre d'épreuves de relais distinctes inscrites × frais de relais |
| Par équipe | 1 × frais d'équipe (si déclaré) |
| Inscription tardive / Frais LSC | 1 × frais (si déclaré) |
| Par épreuve individuelle | 1 par athlète inscrit dans cette épreuve × frais d'épreuve |
| Par épreuve de relais | 1 par équipe dans cette épreuve × frais d'épreuve de relais |

Les éléments avec un tarif nul ou une quantité nulle sont omis de la facture.

---

# Guide Responsable de club

## Connexion

Entrer le NIP du club sur la page de connexion. La page **Athlètes** s'affiche, montrant uniquement les athlètes de votre club.

> Si vous n'avez pas encore reçu votre NIP, demander à l'organisateur de vous envoyer un courriel d'invitation. Cliquer sur le lien dans le courriel pour révéler votre NIP.

## Liens NIP sécurisés

Lorsque l'organisateur envoie une invitation, vous recevez un courriel avec un lien à usage unique. Cliquer sur le lien affiche le NIP de votre club sur une page sécurisée. Le lien expire après 48 heures et ne peut être utilisé qu'une seule fois. Conservez votre NIP en lieu sûr — vous en aurez besoin pour vous connecter.

## Consulter les athlètes

La page **Athlètes** liste tous les athlètes de votre club avec nom, genre, date de naissance et numéro de licence. Utiliser la zone de recherche pour filtrer par nom.

### Ajouter un athlète

Cliquer **+ Ajouter athlète**, remplir prénom, nom, genre, date de naissance et licence NRAN, puis sauvegarder.

### Modifier un athlète

Cliquer **Modifier** à côté du nom de l'athlète pour mettre à jour ses informations.

### Supprimer un athlète

Cliquer **Supprimer** à côté du nom d'un athlète. Ceci supprime l'athlète, toutes ses inscriptions et ses meilleurs temps (confirmation requise).

## Inscrire un athlète

Cliquer sur le nom d'un athlète pour ouvrir la page **Inscription** de cet athlète.

### Épreuves individuelles

La section **Épreuves individuelles** liste toutes les épreuves disponibles en fonction du genre. Pour chaque épreuve :

- **Catégorie** — groupe d'âge suggéré automatiquement selon l'âge de l'athlète et l'année de la compétition (10-, 11-12, 13-14, 15-18, Open). Masters n'est jamais suggéré automatiquement.
- **Meilleur temps 50m / Meilleur temps 25m** — affiché en lecture seule depuis les meilleurs temps de l'athlète. Les temps de plus de 18 mois sont considérés comme expirés et n'apparaissent pas.
- **Temps d'inscription** — pré-rempli à partir du meilleur temps correspondant à la taille du bassin de la compétition ; modifiable
- Cocher la case de l'épreuve pour inscrire ; décocher pour désincrire

### Épreuves de relais

La section **Relais** liste les épreuves de relais. Un club ne peut former qu'une équipe de relais par style. Si un autre athlète de votre club est déjà inscrit à un relais, l'épreuve est verrouillée pour les autres athlètes avec une note indiquant qui s'est inscrit en premier.

### Code d'âge

L'âge est calculé au 31 décembre de l'année de la compétition. L'application suggère automatiquement le bon groupe d'âge. Vous pouvez changer la catégorie dans le menu déroulant si nécessaire (ex. : pour la catégorie Open).

---

# Gestion des données (Admin)

Accéder à la page **Gestion des données** depuis la barre de navigation (Admin seulement).

## Fusion de clubs

Si le même club apparaît sous différents noms (ex. : en raison de variations lors des importations entre compétitions), utiliser le tableau **Fusion de clubs** pour associer les doublons à leur entrée canonique.

- Chaque ligne affiche un nom de club dans la colonne **De** et un menu déroulant dans la colonne **Vers**
- Définir le club **Vers** sur la version canonique pour tout doublon ; les lignes avec une fusion en attente sont surlignées en jaune
- Cliquer **Résoudre** pour fusionner — tous les athlètes et inscriptions du club « De » sont déplacés vers le club « Vers », et le club « De » est supprimé
- **Cette action est irréversible**

## Fusion de styles d'épreuves

Si les meilleurs temps font référence à différents identifiants de style pour la même épreuve (possible lors d'importations depuis différentes bases SPLASH), utiliser **Fusion de styles d'épreuves** pour les consolider.

- Associer les identifiants de style divergents à l'identifiant canonique ; les changements en attente sont surlignés en jaune
- Cliquer **Résoudre** — les meilleurs temps sont fusionnés en conservant le temps le plus rapide par taille de bassin

## Exporter toutes les données (Inscriptions)

Cliquer **Télécharger les inscriptions (.lxf)** pour exporter un fichier Lenex contenant tous les clubs, athlètes et meilleurs temps. C'est l'équivalent de la fonction « Exporter inscriptions » de SPLASH. Sauvegarder ce fichier pour l'utiliser comme point de départ pour la prochaine compétition (le téléverser dans la page Admin au début de la saison).

---

# Cycle de vie de la saison

## Démarrer une nouvelle saison

1. **Exporter toutes les données** depuis Gestion des données → Télécharger les inscriptions (.lxf) — sauvegarder comme fichier de base
2. Exécuter **Réinitialiser la compétition** dans la page Admin pour effacer la compétition en cours
3. Téléverser le fichier de base (étape 1) via Admin → Téléverser Lenex pour restaurer les clubs, athlètes et meilleurs temps

Alternativement, exporter le fichier `.lxf` d'inscriptions directement depuis SPLASH après importation des résultats de la saison en cours, puis le téléverser pour initialiser la nouvelle saison.

## Démarrer une nouvelle compétition (en cours de saison)

Si vous organisez plusieurs compétitions par saison et souhaitez effacer les inscriptions sans réinitialiser les clubs :

1. Exécuter **Réinitialiser la compétition** — ceci supprime les inscriptions, les épreuves, la date limite et la désignation de l'organisateur
2. L'organisateur recommence le processus de configuration (Étapes 2–6 du Guide rapide du flux de travail)

## Réinitialiser tous les NIPs de club

Utiliser **Régénérer tous les NIPs** dans la page Admin. Tous les responsables devront recevoir de nouveaux NIPs via le processus d'invitation. Utile entre les saisons lorsque de nouveaux responsables ont pris en charge des comptes de club.

---

# Dépannage

## Athlète absent de la page d'inscription

- Vérifier que la compétition a été téléversée (bannière verte dans la page Organisateur)
- Vérifier que le genre de l'athlète correspond au genre de l'épreuve
- Vérifier que la date limite d'inscription n'est pas passée (les inscriptions sont verrouillées après la clôture)

## Temps d'inscription non pré-rempli

Le temps d'inscription se pré-remplit depuis le meilleur temps de l'athlète pour la taille de bassin correspondant à la compétition (LCM = 50m, SCM = 25m). Si aucun meilleur temps n'existe pour cette taille de bassin, le champ sera vide. Entrer le temps manuellement.

## Courriel d'invitation non reçu

- Vérifier que le courriel du club est correctement défini dans Admin → Gestion des clubs
- Demander à l'organisateur de renvoyer l'invitation
- Vérifier le dossier courrier indésirable / spam
- Les liens NIP expirent après 48 heures — une nouvelle invitation doit être envoyée si le lien a expiré

## Erreur de facture Stripe

- Vérifier que le compte Stripe est connecté (indicateur vert dans la page Organisateur)
- Le club doit avoir une adresse courriel valide
- Les boutons de facturation ne sont actifs qu'après le passage de la date limite d'inscription

## Impossible de téléverser la structure de la compétition

- Le fichier doit être un fichier `.lxf` Lenex valide exporté depuis SPLASH via Transferts → Exporter l'invitation
- Si une compétition est déjà chargée, confirmer l'avertissement de remplacement

---

# Référence

## Résumé des pages

| Page | Rôle | Actions principales |
|------|------|---------------------|
| Athlètes | Tous | Consulter/ajouter/modifier/supprimer des athlètes, ouvrir l'inscription |
| Inscription | Tous | Inscrire un athlète aux épreuves, définir les temps d'inscription |
| Organisateur | Admin, Organisateur | Téléverser compétition, date limite, invitations, export, factures |
| Admin | Admin | Téléverser Lenex, gérer les clubs, désigner l'organisateur, réinitialiser, changer NIP |
| Gestion des données | Admin | Fusion clubs/styles, exporter inscriptions |

## Raccourcis clavier / interface

- Bascule de langue : bouton FR / EN dans la barre de navigation, en haut à droite
- Déconnexion : bouton **Déconnexion** dans la barre de navigation

## Variables d'environnement

| Variable | Fonction | Défaut |
|----------|---------|--------|
| `ADMIN_PIN` | NIP de connexion Admin | `314159` |
| `RESEND_API_KEY` | Clé API Resend pour les courriels d'invitation | — |
| `RESEND_FROM_EMAIL` | Adresse d'expéditeur pour les courriels | — |
| `APP_BASE_URL` | URL publique utilisée dans les liens des courriels | — |
| `SECRET_KEY` | Clé Fernet pour chiffrer les NIPs dans les liens sécurisés | — |
| `STRIPE_API_KEY` | Clé secrète Stripe pour la génération de factures | — |
| `MEET_TEMPLATE` | Chemin vers le fichier .lxf modèle servi aux organisateurs | `/app/templates/meet.lxf` |
| `BEST_TIME_MAX_AGE_MONTHS` | Mois avant qu'un meilleur temps soit considéré périmé et supprimé | `18` |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL (définie par Docker Compose) | — |
