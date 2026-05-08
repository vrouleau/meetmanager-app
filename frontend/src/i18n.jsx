import { createContext, useContext, useState } from 'react'

const translations = {
  en: {
    athletes: "Athletes",
    admin: "Admin",
    logout: "Logout",
    login_title: "Meet Manager",
    login_prompt: "Enter your club PIN",
    login_btn: "Login",
    invalid_pin: "Invalid PIN",
    search: "Search...",
    edit: "Edit",
    delete: "Delete",
    add_athlete: "+ Add Athlete",
    new_club: "+ New club",
    delete_club: "Delete club",
    reset_pin: "Reset PIN",
    first_name: "First Name",
    last_name: "Last Name",
    gender: "Gender",
    dob: "DOB",
    nran: "NRAN",
    club: "Club",
    save: "Save",
    cancel: "Cancel",
    individual_events: "Individual Events",
    relays: "Relays",
    event: "Event",
    category: "Category",
    best_time: "Best Time",
    entry_time: "Entry Time",
    teammates: "Teammates",
    upload_meet: "Upload Meet Structure (.lxf)",
    upload_meet_desc: "Import event structure from a SPLASH meet export. Required before registering.",
    upload_entries: "Upload Entries (.lxf)",
    upload_entries_desc: "Import clubs and athletes from a SPLASH entries export.",
    upload_results: "Upload Results (.lxf)",
    upload_results_desc: "Import best times from a SPLASH results export.",
    export: "Export Registrations",
    export_desc: "Download Lenex .lxf with all current registrations.",
    download_lxf: "Download .lxf",
    change_admin_pin: "Change Admin PIN",
    regen_pins: "Regenerate All Club PINs",
    regen_pins_desc: "Generate new PINs for all clubs. Old PINs will stop working.",
    flush_reg: "Flush All Registrations",
    flush_reg_desc: "Remove all event registrations (keeps athletes and best times).",
    meet: "Meet",
    no_meet: "No meet uploaded yet",
    uploaded: "uploaded",
    events: "events",
  },
  fr: {
    athletes: "Athlètes",
    admin: "Admin",
    logout: "Déconnexion",
    login_title: "Meet Manager",
    login_prompt: "Entrez votre PIN de club",
    login_btn: "Connexion",
    invalid_pin: "PIN invalide",
    search: "Rechercher...",
    edit: "Modifier",
    delete: "Supprimer",
    add_athlete: "+ Ajouter athlète",
    new_club: "+ Nouveau club",
    delete_club: "Supprimer club",
    reset_pin: "Réinitialiser PIN",
    first_name: "Prénom",
    last_name: "Nom",
    gender: "Sexe",
    dob: "DDN",
    nran: "NRAN",
    club: "Club",
    save: "Enregistrer",
    cancel: "Annuler",
    individual_events: "Épreuves individuelles",
    relays: "Relais",
    event: "Épreuve",
    category: "Catégorie",
    best_time: "Meilleur temps",
    entry_time: "Temps d'inscription",
    teammates: "Équipiers",
    upload_meet: "Téléverser structure (.lxf)",
    upload_meet_desc: "Importer la structure depuis un export SPLASH. Requis avant l'inscription.",
    upload_entries: "Téléverser inscriptions (.lxf)",
    upload_entries_desc: "Importer clubs et athlètes depuis un export SPLASH.",
    upload_results: "Téléverser résultats (.lxf)",
    upload_results_desc: "Importer les meilleurs temps depuis un export SPLASH.",
    export: "Exporter les inscriptions",
    export_desc: "Télécharger le fichier Lenex .lxf avec toutes les inscriptions.",
    download_lxf: "Télécharger .lxf",
    change_admin_pin: "Changer le PIN admin",
    regen_pins: "Régénérer tous les PINs",
    regen_pins_desc: "Générer de nouveaux PINs pour tous les clubs.",
    flush_reg: "Effacer toutes les inscriptions",
    flush_reg_desc: "Supprimer toutes les inscriptions (garde athlètes et temps).",
    meet: "Compétition",
    no_meet: "Aucune compétition téléversée",
    uploaded: "téléversé",
    events: "épreuves",
  },
}

const LangContext = createContext()

export function LangProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem('lang') || 'fr')

  function toggle() {
    const next = lang === 'fr' ? 'en' : 'fr'
    setLang(next)
    localStorage.setItem('lang', next)
  }

  return (
    <LangContext.Provider value={{ t: translations[lang], lang, toggle }}>
      {children}
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}
