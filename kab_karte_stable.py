import os
import sqlite3
import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import folium_static
import pandas as pd
import random  # Für die zufällige Farberzeugung

# Konfiguration
DB_PATH = 'vertriebsgebiete.db'
PLZ_GEOJSON_PATH = 'plz.geojson'
ADMIN_PASSWORD = "admin123"  # Einfaches Passwort ohne Hashing


# Funktion zur Initialisierung der Datenbank
def initialize_database(db_path=DB_PATH, geojson_path=PLZ_GEOJSON_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Vertriebler-Tabelle erstellen
    c.execute('''
        CREATE TABLE IF NOT EXISTS vertriebler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT
        )
    ''')

    # PLZ-Tabelle erstellen und mit Vertrieblern verknüpfen
    c.execute('''
        CREATE TABLE IF NOT EXISTS plz_region (
            region_name TEXT PRIMARY KEY,
            vertriebler_id INTEGER,
            FOREIGN KEY(vertriebler_id) REFERENCES vertriebler(id)
        )
    ''')

    conn.commit()

    # Prüfen, ob bereits PLZ-Daten in plz_region vorhanden sind
    c.execute("SELECT COUNT(*) FROM plz_region")
    count = c.fetchone()[0]
    if count == 0:
        st.sidebar.info("Initialisiere PLZ-Regionen in der Datenbank...")
        try:
            geodaten = gpd.read_file(geojson_path)
        except Exception as e:
            st.sidebar.error(f"Fehler beim Laden der GeoJSON-Daten: {e}")
            st.sidebar.stop()

        # Iteriere über die Features und füge PLZ hinzu
        for idx, row in geodaten.iterrows():
            region_name = row['plz'] if 'plz' in row else f"PLZ {idx}"
            try:
                # Einfügen der PLZ mit vertriebler_id als NULL
                c.execute("INSERT INTO plz_region (region_name, vertriebler_id) VALUES (?, NULL)", (region_name,))
            except sqlite3.IntegrityError:
                # PLZ ist bereits vorhanden
                pass

        conn.commit()
        st.sidebar.success("PLZ-Regionen erfolgreich in die Datenbank eingefügt.")
    else:
        st.sidebar.info("PLZ-Regionen sind bereits in der Datenbank vorhanden.")

    conn.close()


# Funktion zum Generieren einer zufälligen Farbe
def generate_random_color():
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))


# Funktion zum Abrufen der zugewiesenen PLZ-Regionen
def get_assigned_regions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT region_name FROM plz_region
        WHERE vertriebler_id IS NOT NULL
    """)
    assigned_regions = [row[0] for row in c.fetchall()]
    conn.close()
    return assigned_regions


# Funktion zum Abrufen aller Vertriebler
def get_all_vertriebler():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM vertriebler ORDER BY name ASC")
    vertriebler = [row[0] for row in c.fetchall()]
    conn.close()
    return vertriebler


# Funktion zur Authentifizierung des Admins
def authenticate_admin(input_password):
    return input_password == ADMIN_PASSWORD


# Funktion zum Zuweisen einer oder mehrerer PLZ an einen Vertriebler
def assign_plz_to_vertriebler(vertriebler_name, plz_list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Prüfen, ob der Vertriebler bereits existiert
    c.execute("SELECT id FROM vertriebler WHERE name = ?", (vertriebler_name,))
    result = c.fetchone()

    if result:
        vertriebler_id = result[0]
    else:
        # Neuer Vertriebler wird erstellt
        color = generate_random_color()
        c.execute("INSERT INTO vertriebler (name, color) VALUES (?, ?)", (vertriebler_name, color))
        vertriebler_id = c.lastrowid

    # PLZ zuweisen
    for plz in plz_list:
        c.execute("UPDATE plz_region SET vertriebler_id = ? WHERE region_name = ?", (vertriebler_id, plz))

    conn.commit()
    st.sidebar.success(f"Vertriebler '{vertriebler_name}' wurde erfolgreich den ausgewählten PLZ zugewiesen.")
    conn.close()


# Funktion zum Aktualisieren eines Vertrieblers
def update_vertriebler_name(old_name, new_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("UPDATE vertriebler SET name = ? WHERE name = ?", (new_name, old_name))
        conn.commit()
        st.sidebar.success(f"Vertriebler '{old_name}' wurde erfolgreich in '{new_name}' umbenannt.")
    except sqlite3.IntegrityError:
        st.sidebar.error(f"Ein Vertriebler mit dem Namen '{new_name}' existiert bereits.")
    finally:
        conn.close()


# Funktion zum Löschen eines Vertrieblers
def delete_vertriebler(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # Setze alle zugewiesenen PLZ auf "unzugewiesen"
        c.execute(
            "UPDATE plz_region SET vertriebler_id = NULL WHERE vertriebler_id = (SELECT id FROM vertriebler WHERE name = ?)",
            (name,))
        # Lösche den Vertriebler
        c.execute("DELETE FROM vertriebler WHERE name = ?", (name,))
        conn.commit()
        st.sidebar.success(f"Vertriebler '{name}' wurde erfolgreich gelöscht.")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Löschen des Vertrieblers: {e}")
    finally:
        conn.close()


# Funktion zum Abrufen der PLZ eines Vertrieblers
def get_vertriebler_plz(vertriebler_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Abrufen der PLZ, die dem Vertriebler zugewiesen wurden
    c.execute("""
        SELECT region_name FROM plz_region
        JOIN vertriebler ON plz_region.vertriebler_id = vertriebler.id
        WHERE vertriebler.name = ?
    """, (vertriebler_name,))

    regions_list = [row[0] for row in c.fetchall()]
    conn.close()
    return regions_list


# Funktion zum Hinzufügen einer Legende zur Karte
def generate_legend_html(vertriebler_colors):
    # Fügt "Unzugewiesen" mit grauer Farbe zur Legende hinzu
    vertriebler_colors['Unzugewiesen'] = '#808080'

    legend_html = '''
    <div style="font-size:14px;">
    <h4>Legende</h4>
    '''
    for vertriebler, color in vertriebler_colors.items():
        legend_html += f'<p style="margin:0;"><span style="background-color:{color};width:20px;height:20px;display:inline-block;margin-right:10px;"></span>{vertriebler}</p>'
    legend_html += '</div>'
    return legend_html


# Funktion zum Anzeigen der PLZ-Karte und der Legende
def show_map(geodaten, highlighted_regions=None):
    # Vertriebler-Farben und Zuordnungen abrufen
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT vertriebler.name, vertriebler.color, plz_region.region_name
        FROM vertriebler
        JOIN plz_region ON vertriebler.id = plz_region.vertriebler_id
        WHERE plz_region.region_name IS NOT NULL
    """)
    region_data = {row[2]: {'color': row[1], 'vertriebler': row[0]} for row in c.fetchall()}

    # Erstellt ein Dictionary mit allen Vertriebler und ihren Farben
    c.execute("SELECT name, color FROM vertriebler")
    vertriebler_colors = {row[0]: row[1] for row in c.fetchall()}

    conn.close()

    # Map initialisieren
    map_center = [51.1657, 10.4515]  # Deutschland-Zentrum
    m = folium.Map(location=map_center, zoom_start=6)

    # Iteriere über die Geodaten und zeichne die Regionen und PLZ
    for idx, row in geodaten.iterrows():
        plz = row['plz']  # Die PLZ aus dem GeoJSON
        region_info = region_data.get(plz, {'color': 'gray', 'vertriebler': 'Unzugewiesen'})
        if highlighted_regions and plz not in highlighted_regions:
            color = 'gray'  # "Unzugewiesen"-Farbe für alle nicht hervorgehobenen Regionen
        else:
            color = region_info['color']
        vertriebler = region_info['vertriebler']
        geometry = row['geometry']  # Geometrie der Region

        # Berechne den Mittelpunkt der Region, um die PLZ zu platzieren
        centroid = geometry.centroid

        # Tooltip-Text erstellen
        tooltip_text = f"<b>Vertriebler:</b> {vertriebler}"

        # Füge die Region zur Karte hinzu
        folium.GeoJson(
            data=row['geometry'],
            style_function=lambda feature, color=color: {
                'fillColor': color,
                'color': 'black',
                'weight': 1,
                'fillOpacity': 0.5
            },
            tooltip=folium.Tooltip(tooltip_text)
        ).add_to(m)

        # Füge die PLZ als Text (DivIcon) direkt auf die Karte hinzu
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=folium.DivIcon(
                html=f'<div style="font-size: 12pt; color: black;"><b>{plz}</b></div>'
            )
        ).add_to(m)

    # Layout mit zwei Spalten: Links die Karte, rechts die Legende
    col1, col2 = st.columns([4, 1])

    # Zeige die Karte in der linken Spalte an
    with col1:
        folium_static(m, width=1600, height=900)

    # Zeige die Legende in der rechten Spalte an
    with col2:
        legend_html = generate_legend_html(vertriebler_colors)
        st.markdown(legend_html, unsafe_allow_html=True)


# Hauptfunktion der Streamlit-App
def main():
    st.set_page_config(page_title="Vertriebsgebiete Manager", layout="wide")

    # Initialisierung der Datenbank
    if 'initialized' not in st.session_state:
        initialize_database()
        st.session_state.initialized = True

    # Geodaten laden und cachen
    @st.cache_data
    def load_geodata():
        try:
            geodaten = gpd.read_file(PLZ_GEOJSON_PATH)
            geodaten['plz'] = geodaten['plz'].astype(str)
            return geodaten
        except Exception as e:
            st.sidebar.error(f"Fehler beim Laden der PLZ-Geodaten: {e}")
            st.stop()

    geodaten = load_geodata()

    # Sidebar Navigation
    seiten = ["Vertriebler-Ansicht", "Admin-Ansicht"]
    wahl = st.sidebar.radio("Seite auswählen", seiten)

    # Variable für hervorgehobene Regionen und zum Anzeigen des "Auswahl zurücksetzen"-Buttons
    highlighted_regions = None
    plz_angezeigt = False  # Flag, um zu verfolgen, ob PLZ-Gebiete angezeigt wurden

    # Vertriebler-Ansicht
    if wahl == "Vertriebler-Ansicht":
        st.sidebar.header("Vertriebler-Ansicht")

        # Abrufen aller Vertriebler für das Dropdown-Menü
        all_vertriebler = get_all_vertriebler()

        if all_vertriebler:
            # Dropdown-Menü mit Vertriebsmitarbeitern
            name = st.sidebar.selectbox("Wählen Sie Ihren Namen:", all_vertriebler)

            if st.sidebar.button("PLZ-Gebiete anzeigen"):
                if name and name.strip() != "":
                    regions_list = get_vertriebler_plz(name.strip())
                    if regions_list:
                        st.sidebar.success(f"Zugewiesene PLZ: {', '.join(regions_list)}")
                        highlighted_regions = regions_list  # Markiere die PLZ des ausgewählten Vertrieblers
                        plz_angezeigt = True  # Setze das Flag auf True
                    else:
                        st.sidebar.error("Keine zugewiesene PLZ gefunden.")
                else:
                    st.sidebar.warning("Bitte wählen Sie einen gültigen Vertriebler aus.")

            # "Auswahl zurücksetzen"-Button, nur anzeigen, wenn PLZ angezeigt wurden
            if plz_angezeigt and st.sidebar.button("Ansicht zurücksetzen"):
                highlighted_regions = None  # Setzt die hervorgehobenen Regionen zurück
                plz_angezeigt = False  # Zurücksetzen des Flags

        else:
            st.sidebar.warning("Es sind derzeit keine Vertriebler verfügbar.")

    # Admin-Ansicht
    elif wahl == "Admin-Ansicht":
        st.sidebar.header("Admin-Ansicht")
        admin_password = st.sidebar.text_input("Admin-Passwort eingeben:", type="password")
        login_button = st.sidebar.button("Login")

        if login_button:
            if authenticate_admin(admin_password):
                st.session_state.admin_authenticated = True
                st.sidebar.success("Authentifizierung erfolgreich.")
            else:
                st.sidebar.error("Falsches Passwort. Zugriff verweigert.")

        # Überprüfen, ob Admin authentifiziert ist
        if 'admin_authenticated' in st.session_state and st.session_state.admin_authenticated:
            admin_seiten = ["PLZ zuweisen", "Vertriebler bearbeiten"]
            admin_wahl = st.sidebar.selectbox("Admin-Funktionen", admin_seiten)

            # PLZ zuweisen
            if admin_wahl == "PLZ zuweisen":
                st.sidebar.subheader("PLZ einem Vertriebler zuweisen")
                vertriebler_name = st.sidebar.text_input("Vertriebler Name", key="vertriebler_name")

                # Laden der verfügbaren PLZ (noch nicht zugewiesen)
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("""
                    SELECT region_name FROM plz_region
                    WHERE vertriebler_id IS NULL
                """)
                zuweisbare_plz = [row[0] for row in c.fetchall()]
                conn.close()

                if not zuweisbare_plz:
                    st.sidebar.warning("Keine PLZ verfügbar, die noch keinem Vertriebler zugewiesen sind.")
                else:
                    plz_selected = st.sidebar.multiselect(
                        "PLZ auswählen",
                        options=zuweisbare_plz,
                        help="Wählen Sie die PLZ aus, die dem Vertriebler zugewiesen werden sollen."
                    )

                    if st.sidebar.button("PLZ zuweisen"):
                        if vertriebler_name.strip() == "":
                            st.sidebar.error("Bitte geben Sie einen gültigen Vertriebler-Namen ein.")
                        elif not plz_selected:
                            st.sidebar.error("Bitte wählen Sie mindestens eine PLZ aus.")
                        else:
                            assign_plz_to_vertriebler(vertriebler_name.strip(), plz_selected)
                            geodaten = load_geodata()

            # Vertriebler bearbeiten
            elif admin_wahl == "Vertriebler bearbeiten":
                st.sidebar.subheader("Vertriebler bearbeiten oder löschen")
                all_vertriebler = get_all_vertriebler()

                if all_vertriebler:
                    vertriebler_choice = st.sidebar.selectbox("Wähle einen Vertriebler zum Bearbeiten oder Löschen",
                                                              all_vertriebler)

                    if vertriebler_choice:
                        new_vertriebler_name = st.sidebar.text_input("Neuer Vertriebsname", value=vertriebler_choice)

                        if st.sidebar.button("Vertriebler aktualisieren"):
                            if new_vertriebler_name.strip():
                                update_vertriebler_name(vertriebler_choice, new_vertriebler_name.strip())
                            else:
                                st.sidebar.error("Der neue Vertriebsname darf nicht leer sein.")

                        # PLZ-Gebiete zuweisen oder entfernen
                        st.sidebar.subheader(f"Zugewiesene PLZ-Gebiete für {vertriebler_choice} bearbeiten")

                        # Lade zugewiesene und verfügbare PLZ-Gebiete
                        assigned_plz = get_vertriebler_plz(vertriebler_choice)

                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        # Verfügbare PLZ-Gebiete, die noch keinem Vertriebler zugewiesen sind
                        c.execute("SELECT region_name FROM plz_region WHERE vertriebler_id IS NULL")
                        available_plz = [row[0] for row in c.fetchall()]
                        conn.close()

                        # Kombiniere zugewiesene und verfügbare PLZ in einer Liste
                        all_plz_options = [{"plz": plz, "status": "zugewiesen"} for plz in assigned_plz] + \
                                          [{"plz": plz, "status": "nicht zugewiesen"} for plz in available_plz]

                        # Multiselect Dropdown für alle PLZ (zugewiesen und nicht zugewiesen)
                        plz_selected = st.sidebar.multiselect(
                            "Zugewiesene PLZ-Gebiete bearbeiten",
                            options=[plz["plz"] for plz in all_plz_options],
                            default=assigned_plz,  # Vorausgewählte PLZ
                            help="Wähle PLZ aus, die zugewiesen oder entfernt werden sollen."
                        )

                        if st.sidebar.button("Änderungen speichern"):
                            if plz_selected:
                                conn = sqlite3.connect(DB_PATH)
                                c = conn.cursor()

                                # Entferne alle ausgewählten PLZ, die vorher zugewiesen waren, aber jetzt abgewählt wurden
                                for plz in assigned_plz:
                                    if plz not in plz_selected:
                                        c.execute("UPDATE plz_region SET vertriebler_id = NULL WHERE region_name = ?",
                                                  (plz,))

                                # Weise die neuen PLZ dem Vertriebler zu, die vorher nicht zugewiesen waren
                                vertriebler_id = c.execute("SELECT id FROM vertriebler WHERE name = ?",
                                                           (vertriebler_choice,)).fetchone()[0]
                                for plz in plz_selected:
                                    if plz not in assigned_plz:
                                        c.execute("UPDATE plz_region SET vertriebler_id = ? WHERE region_name = ?",
                                                  (vertriebler_id, plz))

                                conn.commit()
                                conn.close()
                                st.sidebar.success("Änderungen erfolgreich gespeichert.")
                            else:
                                st.sidebar.error("Bitte wähle mindestens eine PLZ aus.")

                        # Vertriebler löschen
                        if st.sidebar.button("Vertriebler löschen"):
                            if st.sidebar.checkbox("Sind Sie sicher, dass Sie den Vertriebler löschen möchten?"):
                                delete_vertriebler(vertriebler_choice)

    # Anzeige der PLZ-Karte
    st.header("PLZ-Gebiete Karte")
    show_map(geodaten, highlighted_regions=highlighted_regions)


if __name__ == "__main__":
    main()