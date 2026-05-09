# Meet Manager — Quick Start Workflow

## Prerequisites

- SPLASH Meet Manager 11 with your meet database (`.mdb`)
- Meet Manager App running (Docker)
- Meet .lxf exported from SPLASH

---

## Step 1 — Export the Meet Invitation from SPLASH

![Export invitation](1_export_invitation.png)

1. Open your meet in SPLASH Meet Manager
2. Go to **Transfers → Export invitation...**
3. Save the `.lxf` file (this is your meet structure)

---

## Step 2 — Upload Meet Structure to Meet Manager App

1. Log in to the Meet Manager App as **Admin** (PIN: admin PIN)
2. In the **Admin** page, upload the `.lxf` file under **Upload Meet**
3. The app loads all events, pool size, and masters flag

---

## Step 3 — Send Invitations to Team Admins

1. In the Admin page, scroll to **Team Invites**
2. Enter each club's team admin email
3. Click **Send PIN** — an email is sent with a one-time secure link to their PIN

---

## Step 4 — Team Admins Register Athletes

![Edit entries](3_editentries.png)

1. Team admin logs in with their club PIN
2. Select an athlete → Registration page opens
3. Check events to register, select category (15-18 / Open / Masters)
4. Best times (50m and 25m) are displayed read-only
5. Entry time is pre-filled from the best time matching the meet's pool size
6. Adjust entry time if needed

---

## Step 5 — Admin Exports Registrations

1. In the Admin page, click **Download .lxf** under Export
2. Save the generated `.lxf` file

---

## Step 6 — Import Entries into SPLASH

![Import entries](2_importentries.png)

1. In SPLASH, go to **Transfers → Import entries...**
2. Select the `.lxf` file exported from Meet Manager App
3. All athletes, clubs, and entry times are imported

---

## Step 7 — After the Meet: Export Results

![Export results](4_exportresults.png)

1. After the competition, in SPLASH go to **Transfers → Export results...**
2. Save the results `.lxf` file

---

## Step 8 — Upload Results to Update Best Times

1. In the Admin page, upload the results `.lxf` under **Upload Results**
2. Best times are updated (fastest of entry time vs. result time, per pool size)
3. These best times will pre-fill entry times for the next meet

---

## Summary

| Step | Action | Tool |
|------|--------|------|
| 1 | Export meet invitation | SPLASH |
| 2 | Upload meet structure | Meet Manager App (Admin) |
| 3 | Send team invitations | Meet Manager App (Admin) |
| 4 | Register athletes | Meet Manager App (Team Admin) |
| 5 | Export registrations | Meet Manager App (Admin) |
| 6 | Import entries | SPLASH |
| 7 | Export results | SPLASH |
| 8 | Upload results / best times | Meet Manager App (Admin) |
