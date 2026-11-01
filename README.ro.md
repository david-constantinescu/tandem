# Tandem

[English](README.md) · **Română**

**Călătoria ta, în tandem.** Aruncă în el orice confirmare, bilet sau captură de ecran. Tandem le citește, construiește
un singur itinerariu liniștit, îți spune ce se suprapune și rezervă ceva doar când spui tu „da”.

**Încearcă:** https://tandem.softhoarders.me → *Explorează demo-ul* (merge cel mai bine pe telefon).

---

## Povestea

Călătoriile nu vin dintr-o bucată. Zborul e un PDF într-o căsuță de mail, hotelul e un email în alta, biletul la muzeu
e o captură de ecran, iar rezervarea la cină stă într-un grup de chat. Undeva între ele e o problemă pe care o vezi abia
când ești în fața ușii greșite: un tur pe jos care se lovește de cină, un check-in care începe la trei ore după ce
aterizezi, un tren care pleacă înainte să se închidă muzeul.

Tandem e prietenul care citește toate astea în locul tău.

- **Îi dai ce ai.** PDF-uri, poze cu o printare, capturi de ecran, emailuri redirecționate, text lipit, un link sau
  acces doar pentru citire la Gmail.
- **Citește cu grijă.** Fiecare detaliu extras vine cu rândul din care a fost luat, ca să-l verifici într-o secundă.
  Dacă nu e sigur, spune asta și te întreabă, nu ghicește.
- **Construiește călătoria.** Rezervările ajung în călătoria potrivită, în ordine, la ora *locală* corectă (un zbor
  Londra–Roma arată ambele ceasuri).
- **Vede problemele.** Suprapuneri, legături imposibile, hoteluri lipsă, rezervări neconfirmate, termene de anulare.
- **Umple golurile.** Întreabă ce poți face sâmbătă după-amiază și se uită la orele pe care chiar le ai libere.
- **Trăiește și în calendar.** Un singur link privat pune toate călătoriile în Apple, Google sau Outlook Calendar și le
  ține la zi când se schimbă planurile. Referințele de rezervare și numele rămân în Tandem.
- **Merge și fără semnal.** Adaugă-l pe ecranul principal și se poartă ca o aplicație: călătoriile și itinerariul se
  deschid în modul avion și spune clar când ceva are nevoie de conexiune.
- **Nu cheltuie niciodată banii singur.** Poate pregăti o rezervare sau poate parcurge un site de rezervări, dar nu se
  cumpără nimic până nu aprobi exact acel lucru. Dacă se schimbă prețul, te întreabă din nou.
- **Poți împărți călătoria cu familia.** Creezi un link, îl trimiți, iar cine îl deschide vede planul, rezervările și
  harta. Nu poate schimba nimic, iar biletele și confirmările rămân private.

Și câteva lucruri pe care nu le face intenționat: nu se preface că o integrare funcționează când nu funcționează, nu
rezolvă CAPTCHA-uri și nu ocolește regulile unui site, nu trimite fișierele tale unei companii de AI dacă nu ai spus că e
în regulă.

### Ce să încerci în demo

Demo-ul e un weekend prelungit la Roma, cu plecare din Craiova. Numele sunt reale (aeroportul Craiova, Wizz Air, Hotel
Santa Maria, Muzeele Vaticanului, Da Enzo al 29); rezervările sunt exemple cu referințe inventate, iar fiecare document
generat spune asta. Fiecare vizitator primește o copie privată, care expiră după o zi. Spațiul demo nu afișează vremea,
pentru că datele sunt fictive; conturile obișnuite primesc prognoza reală.

1. **Acasă** e un singur ecran: călătoria ca un tichet de îmbarcare, ce urmează și o linie de alertă.
2. **Călătorii → o călătorie** are paginatorul de zile: fiecare zi arată ce e planificat. Butonul de verificări deschide
   știrile locale despre greve și proteste și suprapunerile găsite de Tandem. Butonul de partajare deschide linkul de
   invitație pentru familie.
3. **Asistentul** face restul, cu carduri în chat:
   - *„E grevă? Pot lua autobuzul?”* citește știri locale reale și le dă linkurile.
   - *„Vreau ceva cultural, dar nu știu exact ce”* îl face să întrebe ce fel, cu răspunsuri pe care le atingi.
   - *„Adaugă cină la Roscioli sâmbătă la 20:00”* o pune în plan și spune cu ce se suprapune.
   - *„Cum ajung de la Craiova la Roma?”* dă Google Maps, Google Flights și site-urile companiilor.
   - *„Ce am rezervat sâmbătă?”* răspunde direct din itinerariu.
4. **Butonul + de la bara de chat → un document de test** trimite un bilet fictiv la Colosseum prin pipeline-ul real de
   citire; asistentul îți spune ce a găsit.

---

## Povestea tehnică

### Forma sistemului

```
SPA React (Vite) ──/api/v1──▶ API Flask ──▶ PostgreSQL ◀── worker (flask worker)
                                 │            ▲  tabela de joburi (FOR UPDATE SKIP LOCKED)
                                 │            │  fișiere criptate (pe Vercel)
                                 ▼            │
                   router AI: Gemini · Z.ai · Groq      agent de browser: motor HTTP · Playwright
```

O singură aplicație Flask servește API-ul (și SPA-ul construit, în producție). Munca lungă rulează într-un worker care
ia joburi dintr-un tabel PostgreSQL cu `SELECT … FOR UPDATE SKIP LOCKED`, deci nu e nevoie de Redis sau Celery. Pe
Vercel aceleași joburi rulează direct în cerere, iar un cron apelează un endpoint protejat pentru verificările
programate.

### De la un fișier la un itinerariu

1. **Încărcare** → originalul se criptează (Fernet) și se stochează (disc local, S3 sau PostgreSQL pe Vercel).
   Duplicatele se prind după hash-ul conținutului.
2. **Extragerea textului** → stratul de text din PDF, OCR Tesseract pentru imagini și scanări, parsare MIME pentru
   `.eml`, DOCX și HTML.
3. **Înțelegerea** → în funcție de setarea de AI a omului (oprit / doar text / fișiere și text), routerul AI trimite
   fișierul original la Gemini, imaginile la modelul gratuit de vedere de la Z.ai sau textul la orice furnizor
   disponibil. Cu AI oprit, lucrează un parser local bazat pe reguli.
4. **Verificarea** → fiecare valoare extrasă e căutată în textul sursă. Fiecare câmp ajunge *găsit în document*,
   *derivat* (de ex. ora de final dintr-o durată scrisă) sau *negăsit*, iar asta arată ecranul de verificare.
5. **Gruparea** → înregistrările se potrivesc cu călătorii după date, locuri și referințe de rezervare, sau se propune
   o călătorie nouă. Actualizările unei rezervări existente (alt check-in, anulare) sunt detectate și aplicate ca
   modificări.
6. **Controlul** → reguli deterministe rulează peste itinerariul cu fusuri orare: suprapuneri, secvențe imposibile,
   timp între sosire și check-in, transport sau cazare lipsă, lucruri neconfirmate, termene de anulare. Niciun model
   nu decide dacă două evenimente se suprapun.

### Asistentul

Un agent care folosește aproximativ douăzeci de unelte (citește călătorii și itinerarii, găsește timp liber, caută
activități, propune rezervări, pornește o sarcină pe un site…). Lucrează pe starea din baza de date, nu pe memoria
chatului. Tot ce are efecte devine o **acțiune** pe care un om trebuie s-o aprobe. Aprobarea e legată de un hash al
propunerii exacte, iar răspunsul furnizorului e verificat înainte ca ceva să fie marcat ca rezervat. Fără chei AI, un
asistent local răspunde la întrebările obișnuite direct din date, fără avertismente.

Este un singur asistent, nu mai mulți: căutarea de activități, agentul de browser, contextul live și planificatorul sunt
toate uneltele lui. Când ceri ceva („adaugă cina la 8”), intră direct în plan. Când ideea e a asistentului, intră ca o
sugestie pe care o poți accepta. Rezervările și plățile așteaptă mereu aprobarea ta.

Răspunsurile apar treptat în chat, iar asistentul nu își spune niciodată numele modelului din spate.

### Context live

| Ce | Sursa | Cheie |
|---|---|---|
| Prognoza pe zilele călătoriei (16 zile înainte): șansa de ploaie, orele ude, „mai bine înăuntru” | [Open-Meteo](https://open-meteo.com) | niciuna |
| Greve, proteste, închideri, alerte meteo, căutate în limba locală | [Google News RSS](https://news.google.com), [GDELT](https://www.gdeltproject.org) ca rezervă | niciuna |
| Căutare web generală pentru asistent | [Tavily](https://tavily.com) (1.000 de căutări gratuite/lună), altfel Google News | `TAVILY_API_KEY`, opțională |
| Cum ajungi din A în B | Google Maps, Google Flights și site-urile oficiale ale operatorilor | niciuna |

Asistentul primește acestea ca unelte (`get_weather`, `check_local_news`, `web_search`, `plan_journey`) cu toată
călătoria în față, deci „ce facem sâmbătă?” ține cont de ploaia de sâmbătă, iar „putem lua autobuzul?” verifică dacă e
grevă. Titlurile sunt linkuri, nu fapte verificate. Asistentul spune de unde le-a citit, iar Tandem renunță la titlurile
despre date trecute.

### Furnizori de AI

| Furnizor | Pentru ce | Regulă |
|---|---|---|
| Gemini | Citit PDF-uri și imagini, asistentul principal | Principal |
| Z.ai (GLM) | Text, un model gratuit de vedere, rezervă | Adițional |
| Groq | Sarcini rapide doar cu text | **Nu primește niciodată fișiere.** Impus în router *și* în clientul furnizorului, cu teste |

Se folosesc doar modele gratuite, dacă nu setezi `AI_ALLOW_PAID_MODELS=true`. Totul se degradează elegant: fără chei,
parserul local și asistentul local, niciodată un răspuns inventat.

### Agentul de browser

Sunt listate 42 de site-uri reale de companii aeriene, feroviare, de autobuz, muzee și galerii. Implicit sunt **doar cu
link**: Tandem nu automatizează site-uri ai căror termeni nu au fost verificați (Ryanair, care interzice asta, rămâne
permanent doar cu link). Un operator poate permite *căutarea* asistată pe fiecare site; agentul verifică atunci
robots.txt, rămâne pe domeniul site-ului, refuză să scrie în câmpuri de parolă sau de plată, se oprește la CAPTCHA și la
autentificare și predă controlul înainte de datele personale. Pe site-urile simulate ale Tandem parcurge tot fluxul
după aprobare, asta arată demo-ul.

### Partajarea călătoriei

Proprietarul creează un link de invitație (valabil 14 zile, poate fi oprit oricând). Cine îl deschide se conectează sau
își face cont, vede despre ce călătorie e vorba și intră cu un buton. Membrii pot vedea planul, rezervările, harta și
suprapunerile, dar nu pot schimba nimic și nu văd documentele (biletele și confirmările au date personale). Linkul e
păstrat criptat, ca proprietarul să-l poată copia din nou, și căutat după HMAC. Un link greșit, expirat sau oprit
răspunde la fel, ca să nu dea de gol ce există. Proprietarul poate scoate oameni, iar oricine poate ieși singur.

### Frontend

React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Radix, Leaflet și [Motion](https://motion.dev) pentru
partea elastică (pastilele care alunecă între taburi, listele care apar pe rând, linia traseului care se desenează
singură). Pe telefon urmează convențiile Apple: zone sigure, bară de taburi, ținte de atingere de 44pt, comutatoare de
mărimea UISwitch, câmpuri de 16px ca iOS să nu mărească, foi de jos în loc de ferestre modale și suport pentru mișcare
redusă.

### Aplicație instalabilă (PWA)

Tandem e o aplicație web progresivă: manifest cu iconițe PNG și maskable și un service worker Workbox
(`vite-plugin-pwa`) care păstrează în cache coaja aplicației și toate paginile, deci pornește fără conexiune.
Răspunsurile API nu sunt niciodată puse în cache de service worker. În schimb, călătoriile, itinerariile, rezervările
și suprapunerile se păstrează pe dispozitiv până la o săptămână, prin `dehydrate`/`hydrate` din TanStack Query
(`frontend/src/lib/offline.ts`). Copia aparține unui singur om și se șterge la deconectare sau când intră altcineva.
Versiunile noi sunt oferite printr-un mesaj „Reîncarcă”, nu schimbate pe nepusă masă. Chrome și Android primesc un
buton nativ de instalare; pe iPhone se arată pașii Share → Add to Home Screen.

### Sincronizare cu calendarul

`/api/v1/calendar` servește fișiere RFC 5545: ore în UTC, ca orice calendar să le arate corect, linii împăturite la 75
de octeți, UID-uri stabile, ca modificările să actualizeze evenimentele în loc să le dubleze. Linkul de abonare conține
un token aleatoriu, păstrat criptat (deci Setările îl pot arăta din nou) și căutat după HMAC; resetarea lui oprește
linkul vechi.

### Securitate și confidențialitate, pe scurt

Sesiuni pe server cu header CSRF, fișiere, tokenuri și extrageri criptate la stocare, consimțământ AI per utilizator
impus pe server, limite de cereri la autentificare și la crearea demo-ului, import de linkuri protejat împotriva SSRF și
extragere atentă la prompt injection (documentele sunt date, niciodată instrucțiuni). Mai multe în
[docs/SECURITY.md](docs/SECURITY.md) și [docs/AI_PRIVACY.md](docs/AI_PRIVACY.md).

---

## Cum îl pornești

Cerințe: Python 3.11, Node 20+, Tesseract (`brew install tesseract`). PostgreSQL vine din binarele incluse în pachetul
`pgserver`, sau folosești orice PostgreSQL 14+.

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt pgserver
scripts/dev-db.sh start                           # PostgreSQL 16 pe :5433
cp .env.example backend/.env                      # setează SECRET_KEY și ENCRYPTION_KEY (comenzile sunt înăuntru)

cd backend
.venv/bin/flask --app app db upgrade
.venv/bin/flask --app app run --port 5050         # terminal 1: API
.venv/bin/flask --app app worker                  # terminal 2: joburi + agentul de browser
npm --prefix ../frontend install
npm --prefix ../frontend run dev                  # terminal 3: http://localhost:5173
```

### Chei

Niciuna nu e obligatorie. Pe scurt:

| Ia asta | Ca să deblochezi |
|---|---|
| `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey), gratuit) | Citirea PDF-urilor și pozelor cu AI, asistentul complet |
| `ZAI_API_KEY` ([Z.ai](https://z.ai/manage-apikey/apikey-list), modele gratuite) | Al doilea furnizor + model gratuit de vedere |
| `GROQ_API_KEY` ([GroqCloud](https://console.groq.com/keys), gratuit; cheile încep cu `gsk_`) | Sarcini rapide cu text |
| `TAVILY_API_KEY` ([Tavily](https://app.tavily.com), 1.000 de căutări gratuite/lună) | Căutare web generală pentru asistent |
| Client Google OAuth | Import Gmail doar pentru citire |
| Credențiale de partener Viator / GetYourGuide / Booking.com / Expedia | Activități și rezervări live |

Vremea (Open-Meteo), știrile locale (Google News, GDELT), locurile (OpenStreetMap) și linkurile de drum nu cer chei.
Lista completă, cu locul de unde iei fiecare cheie și ce activează, e în [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).
`flask --app app env-status` arată ce are mediul tău (fără să afișeze secrete), iar `scripts/vercel-env-push.sh` copiază
cheile în Vercel fără să le afișeze.

### Teste

```bash
cd backend && .venv/bin/python -m pytest      # 164 de teste pe un PostgreSQL real; furnizorii sunt simulați
cd frontend && npx vitest run && npx tsc -b --noEmit
```

### Publicare

- **Docker:** `docker compose up -d --build` pornește PostgreSQL, Redis, migrările, aplicația web, workerul de joburi și
  un worker de browser Playwright.
- **Vercel:** `api/index.py` e punctul de intrare serverless, SPA-ul se servește static, joburile rulează direct în
  cerere, fișierele se stochează criptate în PostgreSQL (Neon), iar un cron rulează verificările programate. Migrările
  se rulează pe baza de date *înainte* de publicare.

Detalii în [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentație

Documentația din `docs/` e în engleză: [Prezentare produs](docs/PRODUCT_OVERVIEW.md) ·
[Arhitectură](docs/ARCHITECTURE.md) · [Mediu și chei](docs/ENVIRONMENT.md) ·
[Schema bazei de date](docs/DATABASE_SCHEMA.md) · [Referință API](docs/API_REFERENCE.md) ·
[Furnizori AI](docs/AI_PROVIDER_CONFIGURATION.md) · [Confidențialitate AI](docs/AI_PRIVACY.md) ·
[Ingestia documentelor](docs/DOCUMENT_INGESTION.md) · [Agent](docs/AGENT_ARCHITECTURE.md) ·
[Aprobări](docs/APPROVAL_SYSTEM.md) · [Agentul de browser](docs/BROWSER_AGENT.md) ·
[Integrări furnizori](docs/PROVIDER_INTEGRATIONS.md) · [Booking.com](docs/BOOKING_COM_INTEGRATION.md) ·
[Expedia](docs/EXPEDIA_INTEGRATION.md) · [Companii aeriene](docs/AIRLINE_INTEGRATIONS.md) ·
[Demo](docs/DEMO_ENVIRONMENT.md) · [Securitate](docs/SECURITY.md) · [Stare](docs/IMPLEMENTATION_STATUS.md)
