import streamlit as st
import pandas as pd
import random
import copy

st.set_page_config(page_title="Hallenplaner", layout="wide")

# --- WASSERZEICHEN ---
st.markdown(
    """
    <style>
    .watermark {
        position: fixed;
        bottom: 15px;
        right: 15px;
        color: rgba(128, 128, 128, 0.5);
        font-size: 14px;
        font-family: sans-serif;
        font-weight: bold;
        z-index: 9999;
        pointer-events: none;
        user-select: none;
    }
    </style>
    <div class="watermark">Planungstool © Fatih</div>
    """,
    unsafe_allow_html=True
)

st.title("SVT-Jugend Hallenbelegungsplaner")
st.markdown("Lege Trainingsdauer, Wuensche und Sperrzeiten uebersichtlich pro Team fest. Das System optimiert die lueckenlose Auslastung (90-Minuten-Bloecke zuerst) und erlaubt manuelle Anpassungen.")

alle_jugenden = ["G-Jugend (Bambini)", "F2-Jugend", "F1-Jugend", "E-Jugend", "D-Jugend"]

@st.cache_data
def lade_basiszeiten(uploaded_file):
    df = pd.read_excel(uploaded_file, sheet_name='Vorschlag Zeiten 2627')
    tage = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']
    
    basiszeiten = {tag: [] for tag in tage}
    gesamter_plan = {tag: {} for tag in tage}
    alle_uhrzeiten = set()
    
    for index, row in df.iterrows():
        if pd.notna(row['Uhrzeit']):
            zeit = str(row['Uhrzeit']).replace(" ", "").replace("-", "–")
            alle_uhrzeiten.add(zeit)
            
            for tag in tage:
                if tag in df.columns:
                    wert = row[tag]
                    if pd.notna(wert):
                        gesamter_plan[tag][zeit] = str(wert)
                        if 'SVT Fußball (Junioren)' in str(wert):
                            basiszeiten[tag].append(zeit)
                    else:
                        gesamter_plan[tag][zeit] = ""
                        
    raster = sorted(list(alle_uhrzeiten))
    return basiszeiten, gesamter_plan, raster

@st.cache_data
def lade_standard_zeiten():
    basiszeiten = {
        'Montag': ['15:30–16:00', '16:00–16:30', '16:30–17:00', '17:00–17:30', '17:30–18:00', '18:00–18:30', '18:30–19:00'],
        'Dienstag': [],
        'Mittwoch': ['16:00–16:30', '16:30–17:00', '17:00–17:30', '17:30–18:00', '18:00–18:30', '18:30–19:00', '19:00–19:30', '19:30–20:00'],
        'Donnerstag': ['16:30–17:00', '17:00–17:30', '17:30–18:00', '18:00–18:30', '18:30–19:00', '19:00–19:30'],
        'Freitag': ['15:00–15:30', '15:30–16:00', '16:00–16:30', '16:30–17:00']
    }
    
    raster = [
        '15:00–15:30', '15:30–16:00', '16:00–16:30', '16:30–17:00',
        '17:00–17:30', '17:30–18:00', '18:00–18:30', '18:30–19:00',
        '19:00–19:30', '19:30–20:00'
    ]
    
    gesamter_plan = {tag: {z: "" for z in raster} for tag in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']}
    
    for tag, zeiten in basiszeiten.items():
        for z in zeiten:
            gesamter_plan[tag][z] = "SVT Fußball (Junioren)"
            
    return basiszeiten, gesamter_plan, raster

def check_valid(tag, zeit, dauer, team, plan, team_tage, wunsch_daten, basiszeiten, tage_index, abstandsregel_aktiv):
    bloecke = dauer // 30
    if zeit not in basiszeiten[tag]: return False
    idx = basiszeiten[tag].index(zeit)
    if idx + bloecke > len(basiszeiten[tag]): return False
    
    kandidaten = basiszeiten[tag][idx:idx+bloecke]
    
    for j in range(1, bloecke):
        if basiszeiten[tag].index(kandidaten[j]) != idx + j:
            return False
            
    for k in kandidaten:
        if plan[tag][k] is not None:
            return False
        if (tag, k) in wunsch_daten[team]['gesperrt']:
            return False
            
    for exist_tag in team_tage[team]:
        if abstandsregel_aktiv:
            if abs(tage_index[tag] - tage_index[exist_tag]) < 2:
                return False
        else:
            if tage_index[tag] == tage_index[exist_tag]:
                return False
                
    # Harte Sperre fuer G-Jugend und F2-Jugend ab 18:30 Uhr
    if team in ["G-Jugend (Bambini)", "F2-Jugend"]:
        start_stunde = int(kandidaten[0].split('–')[0].split(':')[0])
        start_min = int(kandidaten[0].split('–')[0].split(':')[1])
        if start_stunde >= 19:
            return False
            
    return True

def place(tag, zeit, dauer, team, plan, team_tage, basiszeiten):
    bloecke = dauer // 30
    idx = basiszeiten[tag].index(zeit)
    kandidaten = basiszeiten[tag][idx:idx+bloecke]
    for k in kandidaten:
        plan[tag][k] = team
    team_tage[team].append(tag)

def auto_place(team, dauer, plan, team_tage, wunsch_daten, basiszeiten, tage_index, logs, label, abstandsregel_aktiv):
    tage_keys = list(basiszeiten.keys())
    random.shuffle(tage_keys)
    
    for tag in tage_keys:
        zeiten = list(basiszeiten[tag])
        random.shuffle(zeiten)
        for zeit in zeiten:
            if check_valid(tag, zeit, dauer, team, plan, team_tage, wunsch_daten, basiszeiten, tage_index, abstandsregel_aktiv):
                place(tag, zeit, dauer, team, plan, team_tage, basiszeiten)
                logs.append(f"{label}-Zuweisung: {team} weicht auf {tag} ab {zeit} aus ({dauer} Min).")
                return True
    return False

def run_monte_carlo(basiszeiten, jugenden, durations, wunsch_daten, abstandsregel_aktiv, iterations=200):
    best_score = -99999
    best_plan = None
    best_logs = []
    best_fehlgeschlagen = []
    
    tage_index = {'Montag': 0, 'Dienstag': 1, 'Mittwoch': 2, 'Donnerstag': 3, 'Freitag': 4}

    for _ in range(iterations):
        plan = {tag: {z: None for z in zeiten} for tag, zeiten in basiszeiten.items()}
        team_tage = {t: [] for t in jugenden}
        logs = []
        fehlgeschlagen = []
        score = 0
        
        reqs = []
        for team in jugenden:
            if durations[team]['t1'] > 0:
                reqs.append({'team': team, 'dauer': durations[team]['t1'], 'type': 'T1', 'wishes': wunsch_daten[team]['w1']})
            if durations[team]['t2'] > 0:
                reqs.append({'team': team, 'dauer': durations[team]['t2'], 'type': 'T2', 'wishes': wunsch_daten[team]['w2']})
                
        # Zuerst mischen, dann nach Dauer sortieren -> 90 Min Bloecke werden zuerst gesetzt
        random.shuffle(reqs)
        reqs.sort(key=lambda x: x['dauer'], reverse=True)
        
        for req in reqs:
            team = req['team']
            dauer = req['dauer']
            wishes = list(req['wishes'])
            placed = False
            
            if wishes:
                random.shuffle(wishes)
                for tag, zeit in wishes:
                    if check_valid(tag, zeit, dauer, team, plan, team_tage, wunsch_daten, basiszeiten, tage_index, abstandsregel_aktiv):
                        place(tag, zeit, dauer, team, plan, team_tage, basiszeiten)
                        logs.append(f"Wunsch erfuellt ({req['type']}): {team} am {tag} ab {zeit}.")
                        score += 50
                        placed = True
                        break
                        
            if not placed:
                if auto_place(team, dauer, plan, team_tage, wunsch_daten, basiszeiten, tage_index, logs, "Auto", abstandsregel_aktiv):
                    score += 20
                else:
                    fehlgeschlagen.append(f"{team} ({req['type']})")
                    score -= 1000 

        if score > best_score:
            best_score = score
            best_plan = copy.deepcopy(plan)
            best_logs = list(logs)
            best_fehlgeschlagen = list(set(fehlgeschlagen))

    return best_plan, best_logs, best_fehlgeschlagen

def farbe_kalender(wert):
    if pd.isna(wert) or wert == "":
        return ""
    if wert in alle_jugenden:
        return "background-color: #ffd966; color: black; font-weight: bold;"
    if wert == "--- Frei ---":
        return "background-color: #93c47d; color: black;"
    return "background-color: #d9d9d9; color: #7f7f7f; font-style: italic;"

def optimiere_t2(ausgewaehlte_teams):
    for team in ausgewaehlte_teams:
        key = f"t2_d_{team}"
        if st.session_state.get(key, 0) == 90:
            st.session_state[key] = 60
    st.session_state.berechnen = True

# --- BENUTZEROBERFLAECHE ---
col_upload, col_standard = st.columns([1, 1])
with col_upload:
    uploaded_file = st.file_uploader("Excel-Belegungsplan hochladen (.xlsx)", type=["xlsx"])
with col_standard:
    st.markdown("<br><br>", unsafe_allow_html=True)
    nutze_standard = st.checkbox("Standard-Hallenplan (ohne Excel) laden", value=False)

daten_geladen = False
if uploaded_file:
    basiszeiten, gesamter_plan, zeit_raster = lade_basiszeiten(uploaded_file)
    daten_geladen = True
elif nutze_standard:
    basiszeiten, gesamter_plan, zeit_raster = lade_standard_zeiten()
    daten_geladen = True

if daten_geladen:
    st.divider()
    
    ausgewaehlte_teams = st.multiselect(
        "Teilnehmende Teams waehlen:",
        options=alle_jugenden,
        default=alle_jugenden
    )
    
    if ausgewaehlte_teams:
        st.subheader("1. Individuelle Teameinstellungen")
        st.write("Klicke auf eine Jugend, um Dauer, Wunschzeiten und Sperren einzustellen.")
        
        # Tabs fuer eine aufgeraeumte Darstellung
        tabs = st.tabs(ausgewaehlte_teams)
        
        # Flache Liste aller verfuegbaren Zeiten erstellen
        alle_zeiten_flach = []
        for tag in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']:
            for z in basiszeiten[tag]:
                alle_zeiten_flach.append(f"{tag} {z}")
                
        durations = {}
        wunsch_daten = {t: {'w1': [], 'w2': [], 'gesperrt': []} for t in ausgewaehlte_teams}
        
        for i, team in enumerate(ausgewaehlte_teams):
            with tabs[i]:
                # Voreinstellungen abhaengig vom Team
                if team == "G-Jugend (Bambini)":
                    def_t1, def_t2 = 60, 0
                elif team == "F2-Jugend":
                    def_t1, def_t2 = 90, 0
                else:
                    def_t1, def_t2 = 90, 90
                
                # Standard-Sperrzeiten fuer G und F2 generieren
                default_sperren = []
                if team in ["G-Jugend (Bambini)", "F2-Jugend"]:
                    for tz in alle_zeiten_flach:
                        z = tz.split(" ", 1)[1]
                        h = int(z.split('–')[0].split(':')[0])
                        m = int(z.split('–')[0].split(':')[1])
                        if h >= 19 or (h == 18 and m >= 30):
                            default_sperren.append(tz)
                
                # Layout innerhalb des Tabs
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**1. Training**")
                    t1_val = st.selectbox("Dauer T1", options=[0, 60, 90], index=[0, 60, 90].index(def_t1), key=f"t1_d_{team}")
                    w1_val = st.selectbox("Wunsch-Startzeit T1", options=["Kein Wunsch"] + alle_zeiten_flach, key=f"w1_{team}")
                    
                    if w1_val != "Kein Wunsch":
                        tag, zeit = w1_val.split(" ", 1)
                        wunsch_daten[team]['w1'].append((tag, zeit))
                        
                with col2:
                    st.markdown("**2. Training**")
                    t2_val = st.selectbox("Dauer T2", options=[0, 60, 90], index=[0, 60, 90].index(def_t2), key=f"t2_d_{team}")
                    w2_val = st.selectbox("Wunsch-Startzeit T2", options=["Kein Wunsch"] + alle_zeiten_flach, key=f"w2_{team}")
                    
                    if w2_val != "Kein Wunsch":
                        tag, zeit = w2_val.split(" ", 1)
                        wunsch_daten[team]['w2'].append((tag, zeit))
                        
                st.markdown("<br>", unsafe_allow_html=True)
                
                gesperrt = st.multiselect(
                    "Sperrzeiten (Zeiten an denen das Team absolut NICHT kann):",
                    options=alle_zeiten_flach,
                    default=default_sperren,
                    key=f"sperr_{team}"
                )
                
                for tz in gesperrt:
                    tag, zeit = tz.split(" ", 1)
                    wunsch_daten[team]['gesperrt'].append((tag, zeit))
                    
                durations[team] = {'t1': t1_val, 't2': t2_val}

        st.divider()
        st.subheader("2. Regel-Einstellungen")
        abstandsregel_aktiv = st.checkbox("1-Tag-Abstandsregel erzwingen", value=True, help="Wenn deaktiviert, duerfen Teams auch an aufeinanderfolgenden Tagen (z.B. Mi und Do) trainieren. Zwei Trainings am identischen Tag sind weiterhin gesperrt.")

        st.divider()
        if st.button("Belegungsplan berechnen und auslosen", type="primary"):
            st.session_state.berechnen = True
            
        if st.session_state.get("berechnen", False):
            belegungsplan, logs, fehlgeschlagen = run_monte_carlo(
                basiszeiten, 
                ausgewaehlte_teams, 
                durations, 
                wunsch_daten,
                abstandsregel_aktiv,
                iterations=200 
            )
            
            if fehlgeschlagen:
                fehl_text = ", ".join(fehlgeschlagen)
                st.toast(f"Planungskonflikt: {fehl_text} konnten nicht vollstaendig zugewiesen werden.")
                st.error(f"WARNUNG: Die folgenden Jugenden konnten aufgrund von Platzmangel nicht vollstaendig zugewiesen werden: {fehl_text}.")
                
                st.button(
                    "Automatische Not-Optimierung (2. Tage aller Teams auf 60 Min kuerzen)", 
                    on_click=optimiere_t2, 
                    args=(ausgewaehlte_teams,),
                    type="secondary"
                )
            else:
                st.success("Alle ausgewaehlten Trainingseinheiten konnten erfolgreich platziert werden!")
            
            # --- INTERAKTIVER ERGEBNIS-KALENDER ZUM MANUELLEN ANPASSEN ---
            kalender_df = pd.DataFrame(index=zeit_raster, columns=['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag'])
            fremd_belegungen_liste = set()
            
            for tag in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']:
                for zeit in zeit_raster:
                    team_belegung = belegungsplan.get(tag, {}).get(zeit)
                    if team_belegung:
                        kalender_df.at[zeit, tag] = team_belegung
                    else:
                        orig = gesamter_plan.get(tag, {}).get(zeit, "")
                        if "SVT Fußball (Junioren)" in orig:
                            kalender_df.at[zeit, tag] = "--- Frei ---"
                        else:
                            kalender_df.at[zeit, tag] = orig
                            if orig != "":
                                fremd_belegungen_liste.add(orig)
                        
            kalender_df = kalender_df.dropna(how='all')
            kalender_df.fillna("", inplace=True)
            
            auswahl_optionen = ["", "--- Frei ---"] + ausgewaehlte_teams + list(fremd_belegungen_liste)
            
            st.subheader("Der fertige Wochenkalender (Manuell anpassbar)")
            st.write("Du kannst die berechneten Trainingszeiten hier direkt in der Tabelle anklicken und über das Dropdown-Menü jederzeit händisch verschieben oder korrigieren.")
            
            col_config_output = {
                tag: st.column_config.SelectboxColumn(
                    tag,
                    options=auswahl_optionen,
                ) for tag in kalender_df.columns
            }
            
            styled_df = kalender_df.style.map(farbe_kalender)
            
            finaler_plan = st.data_editor(
                styled_df, 
                column_config=col_config_output, 
                use_container_width=True,
                key="finaler_editor"
            )
            
            st.subheader("Auswertungs-Protokoll (Auslosung & Zuweisung)")
            for log in logs:
                st.text(log)
else:
    st.info("Bitte lade eine Excel-Datei hoch oder aktiviere den Standard-Hallenplan, um zu beginnen.")
