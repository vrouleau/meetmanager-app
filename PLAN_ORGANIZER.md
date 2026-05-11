# Organizer Role - Final Implementation Plan

## Key Design Decisions
- Organizer = a team coach whose club is flagged as organizer (same PIN, elevated access)
- One organizer per meet, designated by admin
- Organizer sees ALL athletes but can only edit OWN team's registrations
- No PIN reset on meet upload — only admin does PIN resets
- "Flush Meet" replaces "Flush Registrations" — resets organizer_club_id + meet info + registrations
- Organizer designation never carries over — flush meet clears it
- "Send Invitation" (not "Send PIN") for button labels
- "Invite All" button sends to all clubs with an email set

## Backend Tasks

### 1. Auth (`backend/app/routers/api.py`)
In `/auth` endpoint, after finding a club by PIN, check if club.id matches AppConfig key `organizer_club_id`. If yes, return `role: "organizer"` instead of `"coach"`.

### 2. Set Organizer
New endpoint `POST /admin/set-organizer` body `{club_id: int}`. Sets AppConfig `organizer_club_id` = club_id. Admin-only.

### 3. Access Control
- `GET /athletes`: organizer can call without club_id filter (sees all)
- `POST /registrations` and `DELETE /registrations/{id}`: still checks that the athlete belongs to the caller's club (organizer restricted to own team)
- Meet upload, closure date, club invite endpoints: accessible by organizer role

### 4. Flush Meet (modify existing `DELETE /registrations`)
- Delete all registrations
- Clear AppConfig keys: meet_filename, meet_uploaded_at, meet_name, meet_course, meet_masters, meet_currency, meet_fees_json, closure_date, organizer_club_id
- Delete all events
- Keep clubs, athletes, best times, PINs intact

### 5. Invite All
`POST /organizer/clubs/invite-all` body `{lang: "fr"|"en"}`. Loop all clubs with admin_email set, call the same send-pin logic for each. Return count sent.

## Frontend Tasks

### 6. Organizer.jsx (`frontend/src/pages/Organizer.jsx`)
New page with:
- Meet info display (moved from Admin)
- Fee summary component (moved from Admin)
- Closure date picker (moved from Admin)
- Meet upload input (moved from Admin)
- Team invite management box:
  - Dropdown of clubs + "Add" button (adds club to invited list)
  - List with checkboxes, club name, email, "Send Invitation" button per row
  - "Delete" button (removes checked clubs — resets their PIN + deletes their registrations)
  - "Invite All" button (sends invitation to all clubs with email)

### 7. Admin.jsx updates
- Remove: meet info, fee summary, closure date, meet upload sections
- Add: "Set as Organizer" button next to team dropdown
- Rename: "Flush Registrations" → "Flush Meet" with updated confirm text
- Keep: status, entries upload, results upload, export, invoices, change admin PIN, regen PINs

### 8. Routing & Nav (App.jsx)
- Add `/organizer` route → Organizer.jsx
- Nav visibility:
  - Admin: Athletes, Organizer, Admin
  - Organizer: Athletes, Organizer
  - Coach: Athletes (filtered to own club)

### 9. i18n (`frontend/src/i18n.jsx`)
Add FR/EN translations for:
- Organizer page title, set organizer, send invitation, invite all, flush meet, team invite box labels

### 10. Test
Verify all three role flows, build compiles.
