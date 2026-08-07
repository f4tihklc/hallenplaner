import streamlit as st
import pandas as pd
import random
import copy

st.set_page_config(page_title="Hallenplaner", layout="wide")

st.title("Hallenbelegungsplaner")
st.markdown("Trage Wuensche und Sperrzeiten direkt in den Kalender ein. Das System lost bei Ueberschneidungen automatisch aus und optimiert die Belegung, um alle Slots maximal zu fuellen.")

alle_jugenden = ["G-Jugend (Bambini)", "F2-Jugend", "F1-Jugend", "E2-Jugend", "E1-Jugend", "D-Jugend"]

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

def check_valid(tag, zeit, dauer, team, plan, team_tage, wunsch_daten, basiszeiten, tage_index):
    bloecke = dauer // 30
    if zeit not in basiszeiten[tag]: return False
    idx = basiszeiten[tag].index(zeit)
    if idx + bloecke > len(basiszeiten[tag]): return False
    
    kandidaten = basiszeiten[tag][idx:idx+bloecke]
    
    # Pruefen, ob die Bloecke direkt hintereinander liegen
    for j in range(1, bloecke):
        if basiszeiten[tag].index(kandidaten[j]) != idx + j:
            return False
            
    # Pruefen auf Belegung und Sperrzeiten
    for k in kandidaten:
        if plan[tag][k] is not None:
            return False
        if (tag, k) in wunsch_daten[team]['gesperrt']:
            return False
            
    # 1-Tag-Abstandsregel
    for exist_tag in team_tage[team]:
        if abs(tage_index[tag] - tage_index[exist_tag]) < 2:
            return False
            
    # Bambini-Sperre ab 19 Uhr
    if team == "G-Jugend (Bambini)":
        start_stunde = int(kandidaten[0].split('–')[0].split(':')[0])
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

def auto_place(team, dauer, plan, team_tage, wunsch_daten, basiszeiten, tage_index, logs, label="Auto"):
    tage_keys = list(basiszeiten.keys())
    random.shuffle(tage_keys)
    
    for tag in tage_keys:
        zeiten = list(basiszeiten[tag])
        random.shuffle(zeiten)
        for zeit in zeiten:
            if check_valid(tag, zeit, dauer, team, plan, team_tage, wunsch_daten, basiszeiten, tage_index):
                place(tag, zeit, dauer, team, plan, team_tage, basiszeiten)
                logs.append(f"{label}-Zuweisung: {team} weicht auf {tag} ab {zeit} aus ({dauer} Min).")
                return True
    return False

def run_monte_carlo(basiszeiten, jugenden, durations, wunsch_daten, iterations=100):
    best_score = -9999
    best_plan = None
    best_logs = []
    best_fehlgeschlagen = []
    
    tage_index = {'Montag': 0, 'Dienstag': 1, 'Mittwoch': 2, 'Donnerstag': 3, 'Freitag': 4}
    target_trainings = {t: 0 for t in jugenden}
    for t in jugenden:
        if durations[t]['t1'] > 0: target_trainings[t] += 1
        if durations[t]['t2'] > 0: target_trainings[t] += 1

    for _ in range(iterations):
        plan = {tag: {z: None for z in zeiten} for tag, zeiten in basiszeiten.items()}
        team_tage = {t: [] for t in jugenden}
        logs = []
        fehlgeschlagen = []
        score = 0
        assigned_count = {t: 0 for t in jugenden}
        
        # 1. Wuensche 1 verteilen (Auslosen durch Zufallsreihenfolge)
        teams_w1 = list(jugenden)
        random.shuffle(teams_w1)
        for team in teams_w1:
            if durations[team]['t1'] == 0: continue
            w1_options = wunsch_daten[team]['w1']
            if not w1_options: continue
            
            random.shuffle(w1_options)
            placed = False
            for tag, zeit in w1_options:
                if check_valid(tag, zeit, durations[team]['t1'], team, plan, team_tage, wunsch_daten, basiszeiten, tage_index):
                    place(tag, zeit, durations[team]['t1'], team, plan, team_tage, basiszeiten)
                    logs.append(f"Wunsch 1 erfuellt: {team} am {tag} ab {zeit}.")
                    assigned_count[team] += 1
                    score += 50
                    placed = True
                    break
            if not placed:
                logs.append(f"Wunsch 1 abgelehnt (Los verloren / Konflikt): {team}.")

        # 2. Wuensche 2 verteilen
        teams_w2 = list(jugenden)
        random.shuffle(teams_w2)
        for team in teams_w2:
            if durations[team]['t2'] == 0: continue
            w2_options = wunsch_daten[team]['w2']
            if not w2_options: continue
            
            random.shuffle(w2_options)
            placed = False
            for tag, zeit in w2_options:
                # W2 erfordert den T2-Dauer-Block
                if check_valid(tag, zeit, durations[team]['t2'], team, plan, team_tage, wunsch_daten, basiszeiten, tage_index):
                    place(tag, zeit, durations[team]['t2'], team, plan, team_tage, basiszeiten)
                    logs.append(f"Wunsch 2 erfuellt: {team} am {tag} ab {zeit}.")
                    assigned_count[team] += 1
                    score += 40
                    placed = True
                    break
            if not placed:
                logs.append(f"Wunsch 2 abgelehnt (Los verloren / Konflikt): {team}.")

        # 3. Lücken mit den fehlenden Einheiten schliessen
        teams_auto = list(jugenden)
        random.shuffle(teams_auto)
        
        for team in teams_auto:
            while assigned_count[team] < target_trainings[team]:
                # Finde heraus, ob T1 oder T2 nachgeholt werden muss
                if assigned_count[team] == 0 and durations[team]['t1'] > 0:
                    naechste_dauer = durations[team]['t1']
                else:
                    naechste_dauer = durations[team]['t2']
                    if naechste_dauer == 0: naechste_dauer = durations[team]['t1']
                
                if auto_place(team, naechste_dauer, plan, team_tage, wunsch_daten, basiszeiten, tage_index, logs, "Rest-Fill"):
                    assigned_count[team] += 1
                    score += 20
                else:
                    break 

        # 4. Auswertung des Durchlaufs
        for team in jugenden:
            if assigned_count[team] < target_trainings[team]:
                fehlgeschlagen.append(team)
                score -= 200 # Harte Strafe, wenn das Team nicht trainieren kann

        # Besten Durchlauf speichern
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
    if "SVT Fußball (Junioren)" in str(wert):
        return "background-color: #93c47d; color: black;"
    return "background-color: #d9d9d9; color: #7f7f7f; font-style: italic;"

def optimiere_t2(ausgewaehlte_teams):
    for team in ausgewaehlte_teams:
        key = f"t2_d_{team}"
        if st.session_state.get(key, 0) == 90:
            st.session_state[key] = 60
    st.session_state.berechnen = True

# --- BENUTZEROBERFLAECHE ---
uploaded_file = st.file_uploader("Excel-Belegungsplan hochladen (.xlsx)", type=["xlsx"])

if uploaded_file:
    basiszeiten, gesamter_plan, zeit_raster = lade_basiszeiten(uploaded_file)
    
    st.divider()
    st.subheader("1. Teilnehmende Teams und Dauer")
    
    ausgewaehlte_teams = st.multiselect(
        "Waehle die Teams aus:",
        options=alle_jugenden,
        default=alle_jugenden
    )
    
    if ausgewaehlte_teams:
        durations = {}
        col1, col2, col3 = st.columns([2, 1, 1])
        col1.write("**Jugend**")
        col2.write("**Dauer T1 (Min)**")
        col3.write("**Dauer T2 (Min)**")
        
        for team in ausgewaehlte_teams:
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.markdown(f"<div style='padding-top: 10px;'><b>{team}</b></div>", unsafe_allow_html=True)
            
            def_t1 = 90 if team == "F2-Jugend" else 60
            def_t2 = 60
            
            t1_key = f"t1_d_{team}"
            if t1_key not in st.session_state: st.session_state[t1_key] = def_t1
            t1_val = c2.selectbox(f"T1 {team}", options=[0, 60, 90], key=t1_key, label_visibility="collapsed")
            
            t2_key = f"t2_d_{team}"
            if t2_key not in st.session_state: st.session_state[t2_key] = def_t2
            t2_val = c3.selectbox(f"T2 {team}", options=[0, 60, 90], key=t2_key, label_visibility="collapsed")
            
            durations[team] = {'t1': t1_val, 't2': t2_val}

        st.divider()
        st.subheader("2. Interaktiver Eingabe-Kalender (Wuensche & Sperrzeiten)")
        st.write("Waehle in der Tabelle aus, wann eine Jugend trainieren moechte oder keinesfalls kann.")

        # Vorbereiten des Kalender-DataFrames fuer die Eingabe
        kalender_rows = []
        for tag in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']:
            for zeit in basiszeiten[tag]:
                kalender_rows.append(f"{tag} {zeit}")
                
        editor_df = pd.DataFrame(index=kalender_rows, columns=ausgewaehlte_teams)
        editor_df.fillna("", inplace=True)
        
        col_config = {
            team: st.column_config.SelectboxColumn(
                team, 
                options=["", "Wunsch 1", "Wunsch 2", "Gesperrt"],
                default=""
            ) for team in ausgewaehlte_teams
        }
        
        edited_df = st.data_editor(editor_df, column_config=col_config, use_container_width=True)

        st.divider()
        if st.button("Belegungsplan erstellen und optimieren", type="primary"):
            # Wuensche aus dem Kalender extrahieren
            wunsch_daten = {t: {'w1': [], 'w2': [], 'gesperrt': []} for t in ausgewaehlte_teams}
            for tag_zeit, row in edited_df.iterrows():
                tag, zeit = tag_zeit.split(" ", 1)
                for team in ausgewaehlte_teams:
                    val = row[team]
                    if val == "Wunsch 1": wunsch_daten[team]['w1'].append((tag, zeit))
                    elif val == "Wunsch 2": wunsch_daten[team]['w2'].append((tag, zeit))
                    elif val == "Gesperrt": wunsch_daten[team]['gesperrt'].append((tag, zeit))
                    
            st.session_state.wunsch_daten = wunsch_daten
            st.session_state.berechnen = True
            
        if st.session_state.get("berechnen", False):
            belegungsplan, logs, fehlgeschlagen = run_monte_carlo(
                basiszeiten, 
                ausgewaehlte_teams, 
                durations, 
                st.session_state.wunsch_daten,
                iterations=100
            )
            
            if fehlgeschlagen:
                fehl_text = ", ".join(fehlgeschlagen)
                st.toast(f"Planungskonflikt: {fehl_text} konnten nicht vollstaendig zugewiesen werden.")
                st.error(f"WARNUNG: Die folgenden Jugenden konnten aufgrund von Platzmangel oder Abstandsregeln nicht an beiden Tagen zugewiesen werden: {fehl_text}. Bitte passe die Trainingsdauer oder Sperrzeiten an.")
                
                st.button(
                    "Automatische Not-Optimierung (2. Tage aller Teams auf 60 Min kuerzen)", 
                    on_click=optimiere_t2, 
                    args=(ausgewaehlte_teams,),
                    type="secondary"
                )
            else:
                st.success("Alle ausgewaehlten Trainingseinheiten konnten erfolgreich in den verfuegbaren Slots untergebracht werden.")
            
            # Kalender erzeugen
            kalender_df = pd.DataFrame(index=zeit_raster, columns=['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag'])
            
            for tag in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag']:
                for zeit in zeit_raster:
                    team_belegung = belegungsplan.get(tag, {}).get(zeit)
                    if team_belegung:
                        kalender_df.at[zeit, tag] = team_belegung
                    else:
                        kalender_df.at[zeit, tag] = gesamter_plan.get(tag, {}).get(zeit, "")
                        
            kalender_df = kalender_df.dropna(how='all')
            kalender_df.fillna("", inplace=True)
            
            st.subheader("Der fertige Wochenkalender")
            styled_df = kalender_df.style.map(farbe_kalender)
            st.dataframe(styled_df, use_container_width=True, height=600)
            
            st.subheader("Auswertungs-Protokoll (Auslosung & Zuweisung)")
            for log in logs:
                st.text(log)