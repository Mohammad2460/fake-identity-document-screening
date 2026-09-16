# Team Guide — SIH26188

**Read this if you are on the team.** You do not need to code. You do not need Claude. Find your role below and follow your page.

---

## Our project in 30 seconds

**Every team member must be able to say this without reading.** Judges can ask anyone.

> "Border officers check thousands of passports and visas by eye, and forgers change photographs, names, dates of birth, and visa stamps. Our system checks a passport or visa in seconds. It doesn't just say *fake* — it tells you **which field was changed** and draws a **red box** around it, and it explains every decision in plain words. It works fully offline, with no internet."

Practise saying it out loud until you can do it in one breath.

---

## The problem we were given (SIH26188, Ministry of Home Affairs)

> Identity documents such as passports, visas etc. can be forged or tampered. Manual verification is time-consuming and can lead to human errors. Forged documents can contain altered photographs, names, DOBs, or visa stamps. High volumes of documents make manual inspection inefficient.

The four forgeries it names — and how we catch each one:

| Forgery | How we catch it |
|---|---|
| Changed **photograph** | The photo area looks "newer" than the rest of the page, and we compare it with the traveller's selfie |
| Changed **name** | The name printed on the page doesn't match the name hidden in the machine-readable lines at the bottom |
| Changed **date of birth** | The hidden check digit no longer adds up, **and** the DOB field looks "newer" than the other fields |
| Forged **visa stamp** | The stamp area looks "newer" than the rest of the visa |
| **Too many documents** | We can check a whole batch and list the riskiest ones first |

---

## Words you will hear (simple meanings)

| Word | What it means |
|---|---|
| **MRZ** | The two lines of letters and `<<<` symbols at the bottom of a passport. Machines read it. |
| **Check digit** | A number inside the MRZ calculated from the other numbers. Change one number and the check digit stops matching. |
| **OCR** | Software that reads the text on a picture. |
| **ELA** (Error Level Analysis) | A way to spot the part of a picture that was edited later. Edited parts react differently when the image is saved again. |
| **Field-level forensics** | Our main idea: we run ELA **on each field separately** (name, DOB, photo, stamp) to find exactly which one was changed. |
| **Risk score** | A number from 0 to 100. **0-29 = CLEAR** (green), **30-64 = REVIEW** (orange), **65-100 = REJECT** (red). |
| **Watchlist** | A list of wanted or sanctioned people. We check if the traveller's name is close to one. |
| **Synthetic data** | Fake documents we make ourselves for testing. |

---

## ⚠️ Rules for everyone

1. **Never use a real ID document.** Not yours, not a friend's, not a photo from the internet. Not even "just to test". Our test documents are made by our own program.
2. **Never invent a number.** If a slide says "98% accurate", we must have measured it. If we didn't measure it, don't write it. Judges catch made-up numbers.
3. **Every fact on a slide needs a source** (a link you can show).
4. **Don't change the code or the GitHub repo.** Send problems to the Lead instead.
5. **Everyone can explain the project in 30 seconds** (see top of page).

---

## Who does what

| # | Role | Name |
|---|---|---|
| 1 | Lead | ________ |
| 2 | Presenter | ________ |
| 3 | Q&A Expert | ________ |
| 4 | Tester | ________ |
| 5 | Research | ________ |
| 6 | Design & Backup | ________ |

**Only 3 people available?** Lead does role 1. One person does roles 2 + 3. One person does roles 4 + 5 + 6.

---

## Role 1 — Lead

You are the only one who uses Claude and GitHub.

- [ ] Run the build with Claude, task by task (progress is in `docs/PROGRESS.md`)
- [ ] Add teammates to the GitHub repo so they can read it: **GitHub → repo → Settings → Collaborators → Add people**
- [ ] Every few hours, tell the team in the group chat what is working now
- [ ] Collect bug reports from the Tester and give them to Claude
- [ ] Keep the demo laptop charged and ready
- [ ] On demo day, run the system **before** walking to the judges

---

## Role 2 — Presenter

You make the slides and speak on stage. **This is one of the highest-scoring jobs.**

### Start now
- [ ] Read the "Our project in 30 seconds" and "The problem" sections above
- [ ] Make slides (8-10 slides is enough):
  1. **Title** — team name, SIH26188, Ministry of Home Affairs
  2. **The problem** — passports and visas are forged; manual checking is slow and error-prone (use a real news story from the Research person)
  3. **The four forgeries** — photo, name, DOB, visa stamp
  4. **Our idea** — not just *fake*, but **which field** was changed, with a red box
  5. **How it works** — diagram from the Design person
  6. **Live demo** (the Lead runs it while you talk)
  7. **Why you can trust it** — every decision explained; works offline; no real personal data
  8. **Limitations** — be honest (see Role 3's list)
  9. **Future scope** — trained AI model, liveness check, connecting to immigration systems
  10. **Thank you / team**

### Then
- [ ] Write a 4-minute speech. Time it with your phone.
- [ ] Practise it **out loud at least 5 times**
- [ ] Do 2 full rehearsals with the Lead running the demo

### Tips
- Show the **red box picture** as big as possible. It is our best moment.
- Say "the system *recommends* review" — never "the system *proves* this person is a criminal".
- Speak slowly. Pause after the red box appears. Let the judges look.

---

## Role 3 — Q&A Expert

Judges will ask hard questions. You answer them.

### Start now
- [ ] Read this whole guide
- [ ] Learn the prepared answers below until you can say them in your own words

### Prepared answers

**"Is this really AI, or just rules?"**
Both, on purpose. We use neural networks (AI) to read the text, find faces and match faces. Then clear rules make the final decision, so an officer can see *why*. A decision nobody can explain is useless to a border officer.

**"How do you know the date of birth was changed?"**
Two independent ways. First, the passport's hidden check digit stops adding up. Second, the DOB area of the picture reacts differently when re-saved than the other fields do — that means it was edited later. We compare each field with the other fields on the *same* page, so we don't need a database of real passports.

**"Can't a smart forger fix the check digit too?"**
Yes, sometimes — check digits catch most changes but not all. That is exactly why we added the second method (field-level forensics). A forger has to beat both.

**"What is your accuracy?"**
Only say a number if the Lead gives you one we actually measured. If we don't have one yet, say: *"We tested every check against known-correct examples. We don't quote an accuracy number we haven't measured on a proper dataset — measuring on the SIDTD research dataset is our next step."* Never make up a number.

**"Where did you get the data? Did you use real passports?"**
No real documents. Our test documents are generated by our own program. For measuring accuracy we use public research datasets made of fake documents (MIDV-2020 and SIDTD), created exactly because real ID data can't be shared.

**"Does it need the internet?"**
No. It runs fully offline on a laptop. No personal data leaves the machine.

**"What if someone uploads a broken or weird file?"**
The system still gives an answer and doesn't crash. You can offer: *"Please try uploading anything you like."*

**"Can it make mistakes?"**
Yes. The tamper check can wrongly flag very sharp text or images that were never JPEGs. That's why it never auto-rejects on that alone — it sends the document to a human officer for review.

**"Why didn't you train your own deep-learning model?"**
In 36 hours there is no ethical, labelled dataset of forged Indian passports to train on, and an unexplainable model is hard for an officer to trust. Training one on the SIDTD dataset is our clear next step.

**"What stops me holding up a photo of someone else to the camera?"**
We ask the traveller to turn their head, and we watch the nose. On a real head the nose sticks out in front of the eyes, so turning it moves the nose sideways away from the middle of the eyes. A flat photo has no nose sticking out, so nothing moves — and we say so, with the number we measured. Be honest about the limit: *"This is a challenge, not full anti-spoofing. A video replay of the right person turning their head would still get through. A dedicated anti-spoofing model is our next step."*

**"How is this better than a human checking?"**
It takes seconds instead of minutes, never gets tired, checks the maths a human can't do by eye, and points the officer directly at the suspicious field.

### Honest limitations (say these before a judge finds them)
- The edit-detection can give false alarms on some images
- Text reading works for English letters only
- Our liveness check is a head-turn challenge, not full anti-spoofing — a video replay could still beat it
- The liveness threshold was measured on computer-generated turns, not on recorded real people
- Not connected to government systems yet

### Practise
- [ ] Ask a friend to read the questions to you in random order
- [ ] Never say "I don't know" alone — say "I'm not sure, but our Lead can explain the technical detail"

---

## Role 4 — Tester

You use our system like a judge would and try to break it.

### Before the website is ready
The website comes later in the build. Until then:
- [ ] Read this guide
- [ ] Write a list of "weird things a judge might do": upload a PDF, upload a photo of a cat, leave the form empty, type a name in capital letters, click submit many times fast, upload a huge photo

### When the Lead says the website is ready
- [ ] Open the website on the demo laptop
- [ ] Try every item on your list
- [ ] Try every sample document the Lead gives you, and write down the result colour (green / orange / red)

### How to report a bug
Send the Lead a message exactly like this:

> **What I did:** Uploaded `03_dob_retyped.jpg` with name "Anna Maria Eriksson"
> **What I expected:** Red box on the date of birth
> **What happened:** Orange result, no red box
> **Screenshot:** (attach)

One bug per message. Short and exact is best.

---

## Role 5 — Research

You find real facts that make our slides believable.

### Start now
- [ ] Find **3 to 5 real news stories or official reports** about fake or tampered passports or visas in India (for example, cases reported at airports or by immigration authorities)
- [ ] For each one, save: the headline, the date, the link, and one sentence on why it matters
- [ ] Find one or two short, reliable explanations of **ICAO Doc 9303** (the international passport standard that defines the MRZ)
- [ ] Find the official pages for the **MIDV-2020** and **SIDTD** datasets and save the links

### Rules
- Only use trustworthy sources: government sites, well-known newspapers, research papers
- **Always keep the link.** A fact without a source doesn't go on a slide.
- If you can't find a real statistic, **don't guess one.** Tell the Presenter "no reliable number found".

### Later
- The Lead may give you **one command** to run that measures our accuracy. Run it exactly as given and send the Lead the output.

### Send to the Presenter
A short document with your facts and links, by the time the Lead asks for slides.

---

## Role 6 — Design & Backup

You make things look clear, and you make sure the demo survives if something goes wrong.

### Start now — architecture diagram
- [ ] Draw one simple diagram (Canva, PowerPoint or paper-and-photo is fine):

```
 Passport / Visa photo  +  traveller details
              │
              ▼
     Read the text (OCR)
              │
   ┌──────────┼───────────┬───────────┬────────────┐
   ▼          ▼           ▼           ▼            ▼
 MRZ       Field-level   Face       Watchlist   Repeat
 check     forensics     match      check       submission
 digits    (red boxes)                          check
   └──────────┴───────────┴───────────┴────────────┘
              │
              ▼
     Risk score 0-100  →  CLEAR / REVIEW / REJECT
              │
              ▼
   Explanation + picture with red boxes
```

- [ ] Give it to the Presenter

### Later — backup plan
- [ ] When the demo works, **record a screen video** of the full demo (about 4 minutes)
- [ ] Save the video on **your phone** and on a **USB stick**
- [ ] Keep a **second laptop** ready in case the demo laptop fails
- [ ] Check the projector at the venue: does the laptop screen show correctly?

---

## Timeline for the team

| When | Who | What |
|---|---|---|
| **Now** | Presenter, Q&A, Research, Design | Start your "Start now" list. Don't wait for the code. |
| **Now** | Tester | Write your list of weird things to try |
| **When the website is ready** | Tester | Test everything, report bugs |
| **When the demo works** | Design | Record the backup video |
| **Before demo day** | Everyone | **2 full rehearsals**: Presenter speaks, Lead runs the demo, Q&A Expert answers practice questions |
| **Night before** | Everyone | Charge devices. Sleep. |

---

## Demo day checklist

- [ ] Laptop charged, charger packed
- [ ] System already running before walking up
- [ ] Sample documents ready to drag in
- [ ] Backup video on phone **and** USB stick
- [ ] **Wi-Fi off** (proves it works offline)
- [ ] Phone notifications off
- [ ] Every member can say the 30-second pitch

---

## Where things are in the repo

You can read all of these on your phone in the GitHub app or website:

| File | What it is |
|---|---|
| `docs/TEAM_GUIDE.md` | This guide |
| `docs/PROGRESS.md` | What is built so far (✅ = done) |
| `CLAUDE.md` | The full project rules and technical summary |

**Questions? Ask the Lead — not Claude.**
