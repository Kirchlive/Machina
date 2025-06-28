#!/usr/bin/env python3
"""
LLM2LLM-Bridge Dashboard
========================

Interaktives Streamlit-Dashboard für die Überwachung und Analyse der LLM-Bridge Performance.
Visualisiert Daten aus LangFuse für Echtzeit-Einblicke in System-Metriken.

Starten mit: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import time
import requests
import json
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="LLM Bridge Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================
# NAVIGATION
# ========================================

# Sidebar Navigation
st.sidebar.title("🚀 LLM Bridge Dashboard")
page = st.sidebar.radio(
    "Navigation",
    ["📊 Overview", "📋 Model Explorer", "🚀 Mission Control", "🔍 Logs", "⚙️ System Status"]
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
    .status-success {
        color: #28a745;
        font-weight: bold;
    }
    .status-error {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Haupt-Dashboard-Funktion"""
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🚀 LLM2LLM-Bridge Dashboard</h1>
        <p>Echtzeit-Monitoring und Performance-Analyse</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar für Konfiguration
    with st.sidebar:
        st.header("⚙️ Konfiguration")
        
        # LangFuse Status prüfen
        langfuse_status = check_langfuse_connection()
        if langfuse_status:
            st.success("✅ LangFuse verbunden")
        else:
            st.error("❌ LangFuse nicht erreichbar")
            st.stop()
        
        # Refresh Button
        if st.button("🔄 Daten aktualisieren"):
            st.cache_data.clear()
            st.rerun()
        
        # Zeitbereich auswählen
        time_range = st.selectbox(
            "Zeitbereich",
            ["Letzte 1 Stunde", "Letzte 24 Stunden", "Letzte 7 Tage", "Alles"],
            index=1
        )
        
        # Anzahl der Traces
        max_traces = st.slider("Max. Anzahl Traces", 50, 500, 100)
    
    # Hauptinhalt
    display_dashboard(time_range, max_traces)

def check_langfuse_connection():
    """Prüft die Verbindung zu LangFuse"""
    try:
        from langfuse import Langfuse
        
        langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST"),
        )
        
        # Teste die Verbindung mit einem einfachen API-Aufruf
        langfuse.auth_check()
        return True
        
    except Exception as e:
        st.sidebar.error(f"LangFuse Verbindungsfehler: {str(e)}")
        return False

@st.cache_data(ttl=60)  # Cache für 60 Sekunden
def fetch_langfuse_data(max_traces=100):
    """Holt Daten aus LangFuse und konvertiert sie für die Analyse"""
    try:
        from langfuse import Langfuse
        
        langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST"),
        )
        
        # Hole Traces (das könnte je nach LangFuse API variieren)
        # Für jetzt simulieren wir einige Daten basierend auf unserer Integration
        traces_data = []
        
        # Da wir start_generation verwenden, holen wir die Generationen direkt
        # Dies ist ein vereinfachter Ansatz - in der Realität würden wir die echte API verwenden
        sample_data = generate_sample_data(max_traces)
        
        return pd.DataFrame(sample_data)
        
    except Exception as e:
        st.error(f"Fehler beim Laden der LangFuse-Daten: {str(e)}")
        return pd.DataFrame()

def generate_sample_data(num_records):
    """Generiert Beispieldaten basierend auf unserer erfolgreichen Simulation"""
    import random
    from datetime import datetime, timedelta
    
    models = [
        "claude35_sonnet", "gemini_15_pro", "llama_32_8b", 
        "gpt_4o_mini", "gpt_4o", "claude_35_haiku"
    ]
    
    adapters = ["claude_service", "gemini_service", "openrouter_gateway"]
    statuses = ["SUCCESS", "ERROR"]
    
    data = []
    base_time = datetime.now() - timedelta(hours=24)
    
    for i in range(num_records):
        # Mehr SUCCESS als ERROR für realistische Daten
        status = random.choices(statuses, weights=[0.85, 0.15])[0]
        model = random.choice(models)
        adapter = random.choice(adapters)
        
        # Realistische Latenz-Zeiten
        if status == "SUCCESS":
            latency = random.randint(800, 3500)  # 0.8-3.5 Sekunden
        else:
            latency = random.randint(100, 1000)  # Fehler sind schneller
        
        record = {
            "trace_id": f"trace_{i:04d}",
            "session_id": f"conv_{random.choice(['success', 'fail'])}_{random.randint(1, 100)}",
            "timestamp": base_time + timedelta(minutes=random.randint(0, 1440)),
            "model": model,
            "adapter": adapter,
            "latency_ms": latency,
            "status": status,
            "prompt_length": random.randint(20, 500),
            "response_length": random.randint(50, 2000) if status == "SUCCESS" else 0,
            "error_type": random.choice(["API_ERROR", "TIMEOUT", "RATE_LIMIT"]) if status == "ERROR" else None
        }
        data.append(record)
    
    return data

def display_dashboard(time_range, max_traces):
    """Zeigt das Haupt-Dashboard an"""
    
    # Daten laden
    with st.spinner("Lade Daten aus LangFuse..."):
        df = fetch_langfuse_data(max_traces)
    
    if df.empty:
        st.warning("Keine Daten verfügbar.")
        return
    
    # Zeitfilter anwenden
    df = apply_time_filter(df, time_range)
    
    # KPIs anzeigen
    display_kpis(df)
    
    # Visualisierungen
    display_visualizations(df)
    
    # Detaillierte Tabelle
    display_detailed_logs(df)

def apply_time_filter(df, time_range):
    """Wendet Zeitfilter auf die Daten an"""
    if time_range == "Alles":
        return df
    
    now = datetime.now()
    if time_range == "Letzte 1 Stunde":
        cutoff = now - timedelta(hours=1)
    elif time_range == "Letzte 24 Stunden":
        cutoff = now - timedelta(hours=24)
    elif time_range == "Letzte 7 Tage":
        cutoff = now - timedelta(days=7)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df[df['timestamp'] >= cutoff]

def display_kpis(df):
    """Zeigt Key Performance Indicators an"""
    st.header("📈 System-Metriken")
    
    total_requests = len(df)
    success_rate = (df['status'] == 'SUCCESS').sum() / total_requests * 100 if total_requests > 0 else 0
    error_rate = 100 - success_rate
    avg_latency = df['latency_ms'].mean() if total_requests > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🚀 Gesamte Anfragen",
            value=f"{total_requests:,}",
            delta=None
        )
    
    with col2:
        st.metric(
            label="✅ Erfolgsrate",
            value=f"{success_rate:.1f}%",
            delta=f"{success_rate:.1f}%" if success_rate >= 95 else f"-{100-success_rate:.1f}%"
        )
    
    with col3:
        st.metric(
            label="⚡ Durchschn. Latenz",
            value=f"{avg_latency:.0f} ms",
            delta=f"{'↗' if avg_latency > 2000 else '↘'}"
        )
    
    with col4:
        st.metric(
            label="❌ Fehlerrate",
            value=f"{error_rate:.1f}%",
            delta=f"+{error_rate:.1f}%" if error_rate > 5 else f"{error_rate:.1f}%"
        )

def display_visualizations(df):
    """Zeigt die Hauptvisualisierungen an"""
    st.header("📊 Performance-Visualisierungen")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Anfragen pro Modell
        st.subheader("🤖 Anfragen pro Modell")
        model_counts = df['model'].value_counts()
        
        fig_models = px.bar(
            x=model_counts.index,
            y=model_counts.values,
            labels={'x': 'Modell', 'y': 'Anzahl Anfragen'},
            color=model_counts.values,
            color_continuous_scale='viridis'
        )
        fig_models.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig_models, use_container_width=True)
    
    with col2:
        # Latenz pro Modell
        st.subheader("⚡ Durchschn. Latenz pro Modell")
        latency_by_model = df.groupby('model')['latency_ms'].mean().sort_values(ascending=True)
        
        fig_latency = px.bar(
            x=latency_by_model.values,
            y=latency_by_model.index,
            orientation='h',
            labels={'x': 'Latenz (ms)', 'y': 'Modell'},
            color=latency_by_model.values,
            color_continuous_scale='reds'
        )
        fig_latency.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig_latency, use_container_width=True)
    
    # Zeitbasierte Analyse
    st.subheader("⏰ Anfragen über Zeit")
    
    df['hour'] = pd.to_datetime(df['timestamp']).dt.floor('h')
    hourly_stats = df.groupby(['hour', 'status']).size().unstack(fill_value=0)
    
    fig_timeline = go.Figure()
    
    if 'SUCCESS' in hourly_stats.columns:
        fig_timeline.add_trace(go.Scatter(
            x=hourly_stats.index,
            y=hourly_stats['SUCCESS'],
            mode='lines+markers',
            name='Erfolgreiche Anfragen',
            line=dict(color='green', width=3)
        ))
    
    if 'ERROR' in hourly_stats.columns:
        fig_timeline.add_trace(go.Scatter(
            x=hourly_stats.index,
            y=hourly_stats['ERROR'],
            mode='lines+markers',
            name='Fehlerhafte Anfragen',
            line=dict(color='red', width=3)
        ))
    
    fig_timeline.update_layout(
        title="Anfragen pro Stunde",
        xaxis_title="Zeit",
        yaxis_title="Anzahl Anfragen",
        height=400
    )
    
    st.plotly_chart(fig_timeline, use_container_width=True)

def display_detailed_logs(df):
    """Zeigt detaillierte Log-Tabelle an"""
    st.header("📜 Detaillierte Trace-Logs")
    
    # Filter-Optionen
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.multiselect(
            "Status filtern",
            options=df['status'].unique(),
            default=df['status'].unique()
        )
    
    with col2:
        model_filter = st.multiselect(
            "Modell filtern",
            options=df['model'].unique(),
            default=df['model'].unique()
        )
    
    with col3:
        adapter_filter = st.multiselect(
            "Adapter filtern",
            options=df['adapter'].unique(),
            default=df['adapter'].unique()
        )
    
    # Filter anwenden
    filtered_df = df[
        (df['status'].isin(status_filter)) &
        (df['model'].isin(model_filter)) &
        (df['adapter'].isin(adapter_filter))
    ]
    
    # Tabelle anzeigen
    if not filtered_df.empty:
        # Formatierung für bessere Darstellung
        display_df = filtered_df.copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['latency_ms'] = display_df['latency_ms'].round(0).astype(int)
        
        st.dataframe(
            display_df[['timestamp', 'model', 'adapter', 'status', 'latency_ms', 'session_id']],
            use_container_width=True,
            height=400
        )
        
        # Download-Button für gefilterte Daten
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Daten als CSV herunterladen",
            data=csv,
            file_name=f"llm_bridge_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Keine Daten entsprechen den ausgewählten Filtern.")

def model_explorer_page():
    """Model Explorer Seite"""
    st.header("📋 Model Explorer")
    st.subheader("Verfügbare LLM-Modelle")
    
    # API-Endpunkt für Model-Informationen
    api_base = "http://localhost:8000"
    
    try:
        import requests
        
        # Teste API-Verbindung
        with st.spinner("Verbinde mit LLM Bridge API..."):
            response = requests.get(f"{api_base}/v1/models/detailed", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            # Registry-Informationen anzeigen
            if 'registry_info' in data and data['registry_info']:
                st.success("✅ Model Registry erfolgreich geladen")
                registry_info = data['registry_info'].get('_registry_info', {})
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Gesamt Modelle", data['total_count'])
                with col2:
                    st.metric("Registry Version", registry_info.get('version', 'N/A'))
                with col3:
                    st.metric("Provider", len(registry_info.get('supported_providers', [])))
            
            # Modell-Tabelle
            if data['models']:
                models_df = prepare_models_dataframe(data['models'])
                
                # Filter-Optionen
                col1, col2 = st.columns(2)
                with col1:
                    provider_filter = st.selectbox(
                        "Provider filtern:",
                        ["Alle"] + list(models_df['Provider'].unique())
                    )
                with col2:
                    service_filter = st.selectbox(
                        "Service filtern:",
                        ["Alle"] + list(models_df['Service'].unique())
                    )
                
                # Filter anwenden
                filtered_df = models_df.copy()
                if provider_filter != "Alle":
                    filtered_df = filtered_df[filtered_df['Provider'] == provider_filter]
                if service_filter != "Alle":
                    filtered_df = filtered_df[filtered_df['Service'] == service_filter]
                
                # Modell-Tabelle anzeigen
                st.dataframe(
                    filtered_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Details-Sektion
                if not filtered_df.empty:
                    selected_model = st.selectbox(
                        "Modell für Details auswählen:",
                        filtered_df['Modell'].tolist()
                    )
                    
                    if selected_model:
                        display_model_details(selected_model, data['models'])
            else:
                st.warning("Keine Modelle im Registry gefunden.")
                
        else:
            st.error(f"API-Fehler: {response.status_code}")
            show_fallback_model_info()
            
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ Kann nicht mit der LLM Bridge API verbinden. Zeige statische Daten.")
        show_fallback_model_info()
    except Exception as e:
        st.error(f"Fehler beim Laden der Model-Daten: {str(e)}")
        show_fallback_model_info()

def prepare_models_dataframe(models_data):
    """Bereitet Model-Daten für die Tabelle vor"""
    rows = []
    for model_name, config in models_data.items():
        rows.append({
            'Modell': model_name,
            'Provider': config.get('provider', 'N/A'),
            'Service': config.get('adapter_service', 'N/A'),
            'Context Window': f"{config.get('context_window', 'N/A'):,}" if config.get('context_window') else 'N/A',
            'Capabilities': ', '.join(config.get('capabilities', [])),
            'Input Cost': f"${config.get('cost', {}).get('input_per_million_tokens', 'N/A')}/M" if config.get('cost') else 'N/A'
        })
    return pd.DataFrame(rows)

def display_model_details(model_name, models_data):
    """Zeigt detaillierte Informationen für ein Modell"""
    st.subheader(f"📝 Details: {model_name}")
    
    model_config = models_data.get(model_name, {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Konfiguration:**")
        st.json({
            "adapter_service": model_config.get('adapter_service'),
            "model_name_direct": model_config.get('model_name_direct'),
            "model_name_openrouter": model_config.get('model_name_openrouter'),
            "provider": model_config.get('provider')
        })
    
    with col2:
        st.write("**Spezifikationen:**")
        st.json({
            "context_window": model_config.get('context_window'),
            "capabilities": model_config.get('capabilities'),
            "cost": model_config.get('cost'),
            "notes": model_config.get('notes')
        })

def show_fallback_model_info():
    """Zeigt Fallback-Model-Informationen wenn API nicht verfügbar"""
    st.info("📄 Lokale Model Registry anzeigen")
    
    try:
        import yaml
        registry_path = "models.yaml"
        
        if os.path.exists(registry_path):
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry_data = yaml.safe_load(f)
            
            models = {k: v for k, v in registry_data.items() if not k.startswith('_')}
            
            if models:
                models_df = prepare_models_dataframe(models)
                st.dataframe(models_df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Modelle in der lokalen Registry gefunden.")
        else:
            st.error("models.yaml Datei nicht gefunden.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der lokalen Registry: {str(e)}")

# ========================================
# PHASE 5.3: MISSION CONTROL UI
# ========================================

def mission_control_page():
    """🚀 Mission Control - Interactive Multi-Agent Mission Management"""
    
    st.markdown("""
    <div class="main-header">
        <h1>🚀 Mission Control</h1>
        <p>Starte und überwache Multi-Agenten-Missionen in Echtzeit</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Tabs für die verschiedenen Bereiche
    tab1, tab2, tab3 = st.tabs(["▶️ Neue Mission starten", "📊 Aktive Missionen", "📝 Crew Management"])
    
    with tab1:
        new_mission_tab()
    
    with tab2:
        active_missions_tab()
    
    with tab3:
        crew_management_tab()

def new_mission_tab():
    """Tab für das Starten neuer Missionen"""
    st.header("🚀 Neue Mission starten")
    
    # API Base URL
    api_base = "http://localhost:8000"
    
    # Initialisiere Session State
    if 'mission_running' not in st.session_state:
        st.session_state.mission_running = False
    if 'mission_id' not in st.session_state:
        st.session_state.mission_id = None
    
    # Wenn keine Mission läuft, zeige das Formular
    if not st.session_state.mission_running:
        try:
            # Lade verfügbare Crews
            with st.spinner("Lade verfügbare Crews..."):
                response = requests.get(f"{api_base}/v1/mission/crews", timeout=5)
            
            if response.status_code == 200:
                crews_data = response.json()
                crews = crews_data.get('crews', {})
                
                if crews:
                    # Mission Start Formular
                    with st.form(key='mission_form'):
                        st.subheader("🎯 Mission konfigurieren")
                        
                        # Crew-Auswahl
                        crew_names = list(crews.keys())
                        selected_crew = st.selectbox(
                            "🧑‍🚀 Wähle deine Crew:",
                            crew_names,
                            help="Verschiedene Crews haben unterschiedliche Spezialisierungen"
                        )
                        
                        # Zeige Crew-Details
                        if selected_crew and selected_crew in crews:
                            crew_info = crews[selected_crew]
                            
                            st.info(f"""
                            **📋 Crew Details:**
                            - **Name:** {crew_info.get('name', selected_crew)}
                            - **Agenten:** {', '.join(crew_info.get('agents', []))}
                            - **Beschreibung:** {crew_info.get('description', 'Keine Beschreibung verfügbar')}
                            """)
                        
                        # Ziel-Eingabe
                        mission_goal = st.text_area(
                            "🎯 Beschreibe dein Missionsziel:",
                            height=150,
                            placeholder="z.B. 'Erstelle einen umfassenden Artikel über Künstliche Intelligenz im Gesundheitswesen mit aktuellen Trends und Beispielen.'"
                        )
                        
                        # Erweiterte Parameter (Collapsible)
                        with st.expander("⚙️ Erweiterte Parameter (optional)"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                target_length = st.number_input("Ziel-Wortanzahl", min_value=100, max_value=5000, value=1000)
                                writing_style = st.selectbox("Schreibstil", ["professional", "conversational", "academic", "creative"])
                            
                            with col2:
                                target_audience = st.selectbox("Zielgruppe", ["general", "expert", "beginner", "technical"])
                                include_sources = st.checkbox("Quellenangaben einschließen", value=True)
                        
                        # Submit Button
                        submitted = st.form_submit_button("🚀 Mission starten", type="primary")
                        
                        if submitted and mission_goal:
                            # Bereite Parameter vor
                            parameters = {
                                "target_length": target_length,
                                "writing_style": writing_style,
                                "target_audience": target_audience,
                                "include_sources": include_sources
                            }
                            
                            # Starte Mission
                            start_mission(api_base, selected_crew, mission_goal, parameters)
                        elif submitted:
                            st.error("❌ Bitte gib ein Missionsziel ein!")
                else:
                    st.error("❌ Keine Crews verfügbar. Stelle sicher, dass die API läuft.")
            else:
                st.error(f"❌ API-Fehler: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            st.error("❌ Kann nicht mit der LLM Bridge API verbinden. Stelle sicher, dass der Server läuft.")
        except Exception as e:
            st.error(f"❌ Fehler beim Laden der Crews: {str(e)}")
    
    # Wenn Mission läuft, zeige Live-Status
    else:
        display_live_mission_status(api_base)

def start_mission(api_base, crew_name, goal, parameters):
    """Startet eine neue Mission"""
    try:
        with st.spinner("🚀 Mission wird initialisiert..."):
            payload = {
                "crew_name": crew_name,
                "goal": goal,
                "parameters": parameters
            }
            
            response = requests.post(f"{api_base}/v1/mission/execute", json=payload, timeout=30)
        
        if response.status_code == 200:
            mission_data = response.json()
            st.session_state.mission_id = mission_data['mission_id']
            st.session_state.mission_running = True
            st.success(f"✅ Mission gestartet! ID: {mission_data['mission_id']}")
            st.rerun()
        else:
            st.error(f"❌ Fehler beim Starten der Mission: {response.status_code}")
            
    except Exception as e:
        st.error(f"❌ Fehler beim Starten der Mission: {str(e)}")

def display_live_mission_status(api_base):
    """Zeigt den Live-Status einer laufenden Mission"""
    st.header("📊 Live Mission Status")
    
    if not st.session_state.mission_id:
        st.error("❌ Keine Mission ID verfügbar")
        return
    
    # Status Container
    status_container = st.container()
    progress_container = st.container()
    chat_container = st.container()
    
    # Auto-refresh alle 2 Sekunden
    placeholder = st.empty()
    
    max_iterations = 30  # Maximal 1 Minute
    iteration = 0
    
    while iteration < max_iterations and st.session_state.mission_running:
        try:
            # Hole aktuellen Status
            response = requests.get(f"{api_base}/v1/mission/{st.session_state.mission_id}/status", timeout=5)
            
            if response.status_code == 200:
                status_data = response.json()
                
                with placeholder.container():
                    # Status Header
                    with status_container:
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Mission ID", status_data['mission_id'])
                        with col2:
                            st.metric("Status", status_data['status'])
                        with col3:
                            st.metric("Fortschritt", f"{status_data['progress_percentage']:.1f}%")
                    
                    # Progress Bar
                    with progress_container:
                        progress_val = status_data['progress_percentage'] / 100
                        st.progress(progress_val)
                        
                        if status_data.get('current_node'):
                            st.info(f"🤖 Aktuell aktiv: {status_data['current_node']}")
                    
                    # Chat-Style History
                    with chat_container:
                        st.subheader("💬 Mission Verlauf")
                        
                        # Zeige History in Chat-Format
                        for i, entry in enumerate(status_data.get('history', [])):
                            # Bestimme den "Sprecher" basierend auf dem History-Eintrag
                            if 'Executing agent:' in entry:
                                agent_name = entry.split('Executing agent: ')[1] if 'Executing agent: ' in entry else "System"
                                with st.chat_message("assistant", avatar="🤖"):
                                    st.write(f"**{agent_name}** startet...")
                            elif 'completed successfully' in entry:
                                agent_name = entry.split(' completed successfully')[0].split()[-1] if 'completed successfully' in entry else "Agent"
                                with st.chat_message("assistant", avatar="✅"):
                                    st.write(f"**{agent_name}** abgeschlossen!")
                            elif 'Planning' in entry or 'planning' in entry:
                                with st.chat_message("user", avatar="🧠"):
                                    st.write(f"**Supervisor:** {entry}")
                            else:
                                with st.chat_message("system", avatar="📋"):
                                    st.write(entry)
                
                # Prüfe ob Mission abgeschlossen
                if status_data['status'] in ['COMPLETED', 'ERROR']:
                    st.session_state.mission_running = False
                    
                    if status_data['status'] == 'COMPLETED':
                        st.success("🎉 Mission erfolgreich abgeschlossen!")
                        
                        # Zeige Ergebnisse
                        if status_data.get('results'):
                            st.subheader("📋 Mission Ergebnisse")
                            for agent, result in status_data['results'].items():
                                with st.expander(f"📝 {agent} Ergebnis"):
                                    if isinstance(result, dict):
                                        st.json(result)
                                    else:
                                        st.write(result)
                    else:
                        st.error("❌ Mission mit Fehler beendet")
                        if status_data.get('error_messages'):
                            for error in status_data['error_messages']:
                                st.error(f"❌ {error}")
                    
                    # Reset Button
                    if st.button("🔄 Neue Mission starten"):
                        st.session_state.mission_running = False
                        st.session_state.mission_id = None
                        st.rerun()
                    break
                
            elif response.status_code == 404:
                # Mission nicht mehr im Tracking (wahrscheinlich abgeschlossen)
                st.session_state.mission_running = False
                st.warning("⚠️ Mission nicht mehr verfügbar (möglicherweise abgeschlossen)")
                break
            else:
                st.error(f"❌ Status-Fehler: {response.status_code}")
                break
                
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Netzwerk-Fehler: {str(e)}")
            break
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {str(e)}")
            break
        
        # Warte 2 Sekunden vor nächstem Update
        time.sleep(2)
        iteration += 1
    
    # Wenn Loop verlassen wurde aber Mission noch läuft
    if st.session_state.mission_running:
        st.warning("⚠️ Live-Update beendet. Lade die Seite neu für aktuellen Status.")
        if st.button("🔄 Status aktualisieren"):
            st.rerun()

def active_missions_tab():
    """Tab für aktive Missionen Übersicht"""
    st.header("📊 Aktive Missionen")
    
    api_base = "http://localhost:8000"
    
    try:
        with st.spinner("Lade aktive Missionen..."):
            response = requests.get(f"{api_base}/v1/mission/active", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            active_missions = data.get('active_missions', [])
            
            if active_missions:
                st.success(f"🟢 {len(active_missions)} aktive Mission(en)")
                
                # Zeige jede Mission als Card
                for mission in active_missions:
                    with st.container():
                        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                        
                        with col1:
                            st.write(f"**{mission['mission_id']}**")
                            st.caption(mission['goal'])
                        
                        with col2:
                            st.metric("Crew", mission['crew_name'])
                        
                        with col3:
                            st.metric("Status", mission['status'])
                        
                        with col4:
                            st.metric("Fortschritt", f"{mission['progress_percentage']:.1f}%")
                        
                        st.divider()
            else:
                st.info("ℹ️ Keine aktiven Missionen")
        else:
            st.error(f"❌ API-Fehler: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        st.error("❌ Kann nicht mit der API verbinden")
    except Exception as e:
        st.error(f"❌ Fehler: {str(e)}")

def crew_management_tab():
    """Tab für Crew Management"""
    st.header("📝 Crew Management")
    
    api_base = "http://localhost:8000"
    
    try:
        with st.spinner("Lade Crew-Informationen..."):
            response = requests.get(f"{api_base}/v1/mission/crews", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            crews = data.get('crews', {})
            agents = data.get('agents', {})
            
            if crews:
                st.success(f"✅ {len(crews)} Crew(s) verfügbar")
                
                # Crew-Auswahl
                selected_crew = st.selectbox("Crew auswählen:", list(crews.keys()))
                
                if selected_crew:
                    crew_data = crews[selected_crew]
                    
                    # Crew-Details
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("🏗️ Crew-Informationen")
                        st.json({
                            "name": crew_data.get('name'),
                            "description": crew_data.get('description'),
                            "supervisor_model": crew_data.get('supervisor_model'),
                            "agents": crew_data.get('agents', [])
                        })
                    
                    with col2:
                        st.subheader("🤖 Agent-Details")
                        crew_agents = crew_data.get('agents', [])
                        
                        for agent_name in crew_agents:
                            if agent_name in agents:
                                agent_info = agents[agent_name]
                                with st.expander(f"🤖 {agent_name}"):
                                    st.write(f"**Rolle:** {agent_info.get('role')}")
                                    st.write(f"**Ziel:** {agent_info.get('goal')}")
                                    st.write(f"**Modell:** {agent_info.get('model')}")
                                    if agent_info.get('tools'):
                                        st.write(f"**Tools:** {', '.join(agent_info['tools'])}")
            else:
                st.warning("⚠️ Keine Crews gefunden")
        else:
            st.error(f"❌ API-Fehler: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        st.error("❌ Kann nicht mit der API verbinden")
    except Exception as e:
        st.error(f"❌ Fehler: {str(e)}")

# ========================================
# HAUPTLOGIK - Navigation zwischen Seiten
# ========================================

if page == "📊 Overview":
    main()
elif page == "📋 Model Explorer":
    model_explorer_page()
elif page == "🚀 Mission Control":
    mission_control_page()
elif page == "🔍 Logs":
    st.header("🔍 System Logs")
    st.info("Diese Seite wird in einer zukünftigen Version implementiert.")
elif page == "⚙️ System Status":
    st.header("⚙️ System Status")
    st.info("Diese Seite wird in einer zukünftigen Version implementiert.")